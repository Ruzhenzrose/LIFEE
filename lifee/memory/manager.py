"""
知识库管理器

核心类，整合文档索引和搜索功能
参考 clawdbot manager.js
"""

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional, Union

from .chunker import Chunk, chunk_markdown
from .embeddings import EmbeddingProvider, GeminiEmbedding, _contains_non_english
from .schema import (
    DELETE_CHUNKS_BY_PATH_SQL,
    DELETE_FILE_SQL,
    DELETE_FTS_BY_PATH_SQL,
    INSERT_CHUNK_SQL,
    INSERT_FILE_SQL,
    INSERT_FTS_SQL,
    SCHEMA_SQL,
    SELECT_FILE_SQL,
)
from .search import SearchResult, hybrid_search


class MemoryManager:
    """
    知识库管理器

    负责文档索引和语义搜索
    """

    def __init__(
        self,
        db_path: Union[str, Path],
        embedding_provider: EmbeddingProvider,
        knowledge_lang: str = "English",
    ):
        """
        初始化管理器

        Args:
            db_path: SQLite 数据库路径
            embedding_provider: 嵌入提供者
        """
        self.db_path = Path(db_path)
        self.embedding = embedding_provider
        self.knowledge_lang = knowledge_lang

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 连接数据库（限制缓存减少内存占用）
        self.db = sqlite3.connect(str(self.db_path))
        self.db.execute("PRAGMA cache_size = -1024")  # 1MB per connection
        self.db.execute("PRAGMA mmap_size = 0")        # 禁用 mmap 避免内存映射
        self._load_vec_extension()
        self._init_schema()

    def _load_vec_extension(self):
        """加载 sqlite-vec 扩展"""
        try:
            import sqlite_vec
            self.db.enable_load_extension(True)
            sqlite_vec.load(self.db)
            self.db.enable_load_extension(False)
            self._has_vec = True
        except (ImportError, Exception) as e:
            print(f"[knowledge] sqlite-vec not available, falling back to brute-force: {e}")
            self._has_vec = False

    def _init_schema(self):
        """初始化数据库表结构"""
        self.db.executescript(SCHEMA_SQL)
        self.db.commit()
        if self._has_vec:
            self._ensure_vec_index()

    def _ensure_vec_index(self):
        """创建 vec0 向量索引表（如果不存在则从 chunks 表迁移）"""
        # 检查 vec 表是否已存在
        exists = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
        ).fetchone()
        if exists:
            return

        # 获取维度（从第一条 embedding 推断）
        row = self.db.execute("SELECT embedding FROM chunks LIMIT 1").fetchone()
        if not row:
            return
        dims = len(json.loads(row[0]))

        # 创建 vec0 虚拟表
        self.db.execute(f"""
            CREATE VIRTUAL TABLE chunks_vec USING vec0(
                embedding float[{dims}] distance_metric=cosine
            )
        """)

        # 从 chunks 表批量导入 embedding
        import struct
        cursor = self.db.execute("SELECT rowid, embedding FROM chunks")
        batch = []
        for rowid, emb_json in cursor:
            emb = json.loads(emb_json)
            blob = struct.pack(f"{len(emb)}f", *emb)
            batch.append((rowid, blob))
            if len(batch) >= 500:
                self.db.executemany(
                    "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)", batch
                )
                batch.clear()
        if batch:
            self.db.executemany(
                "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)", batch
            )
        self.db.commit()
        print(f"[knowledge] Built vec index: {dims}d")

    def _file_hash(self, path: Path) -> str:
        """计算文件内容的 SHA256 哈希"""
        content = path.read_text(encoding="utf-8")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _chunk_id(
        self,
        path: str,
        start_line: int,
        end_line: int,
        chunk_hash: str,
        model: str,
    ) -> str:
        """生成 chunk ID"""
        key = f"{path}:{start_line}:{end_line}:{chunk_hash}:{model}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _stable_path_key(path: Path) -> str:
        """用相对于 knowledge 目录的路径作为稳定标识

        例如 books/managing-oneself-full.txt
        不管部署在哪台机器都一样，也不会因子目录同名文件冲突。
        """
        parts = path.parts
        # 找到 "knowledge" 目录之后的部分
        for i, p in enumerate(parts):
            if p == "knowledge":
                return "/".join(parts[i + 1:])
        # fallback: 用最后两级
        return "/".join(parts[-2:]) if len(parts) >= 2 else path.name

    def _needs_reindex(self, path: Path) -> bool:
        """检查文件是否需要重新索引"""
        key = self._stable_path_key(path)
        cursor = self.db.execute(SELECT_FILE_SQL, (key,))
        row = cursor.fetchone()

        if row is None:
            return True

        _, stored_hash, stored_mtime, stored_size = row
        current_hash = self._file_hash(path)

        return stored_hash != current_hash

    async def index_file(
        self,
        path: Path,
        force: bool = False,
        max_tokens: int = 400,
        overlap_tokens: int = 80,
    ) -> int:
        """
        索引单个文件

        Args:
            path: 文件路径
            force: 强制重新索引
            max_tokens: 每块最大 token 数
            overlap_tokens: 重叠 token 数

        Returns:
            索引的 chunk 数量
        """
        path = Path(path)

        if not path.exists():
            return 0

        # 检查是否需要重新索引
        if not force and not self._needs_reindex(path):
            return 0

        # 读取文件并分块
        content = path.read_text(encoding="utf-8")
        chunks = chunk_markdown(content, max_tokens, overlap_tokens)

        if not chunks:
            return 0

        # 生成嵌入向量（先生成，成功后再删旧数据，避免速率限制导致数据丢失）
        texts = [chunk.text for chunk in chunks]
        embeddings = await self.embedding.embed_batch(texts)

        # 验证 embedding 完整性
        if len(embeddings) != len(chunks):
            return 0  # embedding 不完整，放弃本次索引，保留旧数据

        # 删除旧数据（embedding 已完整生成，安全删除）
        path_str = self._stable_path_key(path)
        self.db.execute(DELETE_FTS_BY_PATH_SQL, (path_str,))
        self.db.execute(DELETE_CHUNKS_BY_PATH_SQL, (path_str,))

        # 插入新数据
        model = self.embedding.model_name
        now = int(time.time())

        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = self._chunk_id(
                path_str,
                chunk.start_line,
                chunk.end_line,
                chunk.hash,
                model,
            )

            # 插入 chunks 表
            self.db.execute(
                INSERT_CHUNK_SQL,
                (
                    chunk_id,
                    path_str,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.hash,
                    model,
                    chunk.text,
                    json.dumps(embedding),
                    now,
                ),
            )

            # 插入 FTS 表
            self.db.execute(
                INSERT_FTS_SQL,
                (
                    chunk.text,
                    chunk_id,
                    path_str,
                    model,
                    chunk.start_line,
                    chunk.end_line,
                ),
            )

        # 更新文件跟踪
        stat = path.stat()
        self.db.execute(
            INSERT_FILE_SQL,
            (
                path_str,
                self._file_hash(path),
                int(stat.st_mtime),
                stat.st_size,
            ),
        )

        self.db.commit()
        return len(chunks)

    async def index_directory(
        self,
        directory: Path,
        pattern: str = "*.md",
        force: bool = False,
    ) -> int:
        """
        索引目录下所有匹配的文件

        Args:
            directory: 目录路径
            pattern: 文件匹配模式
            force: 强制重新索引

        Returns:
            总共索引的 chunk 数量
        """
        directory = Path(directory)

        if not directory.exists():
            return 0

        total_chunks = 0
        for path in directory.rglob(pattern):
            if path.is_file():
                chunks = await self.index_file(path, force=force)
                total_chunks += chunks

        return total_chunks

    async def search(
        self,
        query: str,
        max_results: int = 6,
        min_score: float = 0.35,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        keyword_query_override: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        搜索知识库

        Args:
            query: 查询文本
            max_results: 最大结果数
            min_score: 最小分数阈值
            vector_weight: 向量搜索权重
            text_weight: 关键词搜索权重
            keyword_query_override: 预翻译的关键词（避免重复翻译）

        Returns:
            搜索结果列表
        """
        # 生成查询向量（用原始 query，跨语言 embedding 效果最好）
        query_embedding = await self.embedding.embed(query)

        # 跨语言 BM25：使用预翻译的关键词，或现场翻译
        keyword_query = keyword_query_override
        if keyword_query is None and isinstance(self.embedding, GeminiEmbedding):
            keyword_query = await self.embedding.translate_to_keywords(query, self.knowledge_lang)

        # 执行混合搜索
        return hybrid_search(
            db=self.db,
            query_embedding=query_embedding,
            query_text=query,
            model=self.embedding.model_name,
            max_results=max_results,
            min_score=min_score,
            vector_weight=vector_weight,
            text_weight=text_weight,
            keyword_query_text=keyword_query,
        )

    def get_stats(self) -> dict:
        """获取索引统计信息"""
        cursor = self.db.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]

        cursor = self.db.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        return {
            "file_count": file_count,
            "chunk_count": chunk_count,
            "embedding_provider": self.embedding.provider_name,
            "embedding_model": self.embedding.model_name,
        }

    def clear(self):
        """清空所有索引"""
        self.db.execute("DELETE FROM chunks_fts")
        self.db.execute("DELETE FROM chunks")
        self.db.execute("DELETE FROM files")
        self.db.commit()

    def close(self):
        """关闭数据库连接"""
        self.db.close()


def format_search_results(results: list[SearchResult]) -> str:
    """
    格式化搜索结果为上下文字符串

    Args:
        results: 搜索结果列表

    Returns:
        格式化的上下文字符串
    """
    if not results:
        return ""

    parts = []
    for i, result in enumerate(results, 1):
        # 提取文件名
        filename = Path(result.path).name
        parts.append(f"[{i}] {filename}:{result.start_line}-{result.end_line}")
        parts.append(result.text.strip())
        parts.append("")

    return "\n".join(parts)
