"""
知识库/RAG 模块

提供文档索引和语义搜索功能

使用示例:
    from lifee.memory import MemoryManager, create_embedding_provider

    # 创建嵌入提供者
    embedding = create_embedding_provider(google_api_key="...")

    # 创建管理器
    manager = MemoryManager("knowledge.db", embedding)

    # 索引目录
    await manager.index_directory("./knowledge")

    # 搜索
    results = await manager.search("查询内容")
"""

from .chunker import Chunk, chunk_markdown
from .embeddings import (
    EmbeddingProvider,
    GeminiEmbedding,
    OpenAIEmbedding,
    create_embedding_provider,
)
from .manager import MemoryManager, format_search_results
from .search import SearchResult, cosine_similarity, hybrid_search
from .user_memory import UserMemory

__all__ = [
    # 用户记忆
    "UserMemory",
    # 管理器
    "MemoryManager",
    "format_search_results",
    # 嵌入
    "EmbeddingProvider",
    "GeminiEmbedding",
    "OpenAIEmbedding",
    "create_embedding_provider",
    # 分块
    "Chunk",
    "chunk_markdown",
    # 搜索
    "SearchResult",
    "hybrid_search",
    "cosine_similarity",
]
