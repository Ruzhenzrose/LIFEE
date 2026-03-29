"""
混合搜索算法

参考 clawdbot hybrid.js / manager-search.js
实现向量搜索 + 关键词搜索的混合
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    path: str
    start_line: int
    end_line: int
    text: str
    score: float
    vector_score: Optional[float] = None
    text_score: Optional[float] = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    计算余弦相似度

    Args:
        a: 向量 A
        b: 向量 B

    Returns:
        相似度 (0-1)
    """
    a_arr = np.array(a)
    b_arr = np.array(b)

    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot / (norm_a * norm_b))


def build_fts_query(query: str, use_or: bool = False) -> str:
    """
    构建 FTS5 查询字符串

    将查询文本转换为 FTS5 MATCH 语法
    例如: "hello world" -> '"hello" AND "world"'（默认）
          "hello world" -> '"hello" OR "world"'（use_or=True）

    Args:
        query: 查询文本
        use_or: 使用 OR 连接（适合翻译后的关键词搜索）
    """
    # 提取词汇（字母数字下划线，或中文字符）
    words = re.findall(r'[\w\u4e00-\u9fff]+', query, re.UNICODE)
    if not words:
        return ""

    connector = " OR " if use_or else " AND "
    terms = [f'"{word}"' for word in words]
    return connector.join(terms)


def search_vector(
    db: sqlite3.Connection,
    query_embedding: list[float],
    model: str,
    limit: int = 24,
) -> list[SearchResult]:
    """
    向量搜索

    在内存中计算余弦相似度

    Args:
        db: SQLite 连接
        query_embedding: 查询向量
        model: 嵌入模型名称
        limit: 返回结果数量

    Returns:
        搜索结果列表（按相似度降序）
    """
    # 获取所有 chunks
    cursor = db.execute(
        """
        SELECT id, path, start_line, end_line, text, embedding
        FROM chunks WHERE model = ?
        """,
        (model,),
    )

    results = []
    for row in cursor:
        chunk_id, path, start_line, end_line, text, embedding_json = row
        embedding = json.loads(embedding_json)

        # 计算余弦相似度
        similarity = cosine_similarity(query_embedding, embedding)

        results.append(SearchResult(
            id=chunk_id,
            path=path,
            start_line=start_line,
            end_line=end_line,
            text=text,
            score=similarity,
            vector_score=similarity,
        ))

    # 按相似度降序排序
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:limit]


def search_keyword(
    db: sqlite3.Connection,
    query: str,
    model: str,
    limit: int = 24,
    use_or: bool = False,
) -> list[SearchResult]:
    """
    关键词搜索（FTS5 BM25）

    Args:
        db: SQLite 连接
        query: 查询文本
        model: 嵌入模型名称
        limit: 返回结果数量
        use_or: 使用 OR 连接关键词

    Returns:
        搜索结果列表（按 BM25 分数）
    """
    fts_query = build_fts_query(query, use_or=use_or)
    if not fts_query:
        return []

    try:
        cursor = db.execute(
            """
            SELECT id, path, start_line, end_line, text, bm25(chunks_fts) AS rank
            FROM chunks_fts
            WHERE chunks_fts MATCH ? AND model = ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (fts_query, model, limit),
        )
    except sqlite3.OperationalError:
        # FTS 查询失败（可能是语法问题）
        return []

    results = []
    for row in cursor:
        chunk_id, path, start_line, end_line, text, rank = row

        # BM25 rank 转换为 0-1 分数
        # rank 是负数，越小（绝对值越大）越相关
        text_score = 1 / (1 + max(0, -rank))

        results.append(SearchResult(
            id=chunk_id,
            path=path,
            start_line=start_line,
            end_line=end_line,
            text=text,
            score=text_score,
            text_score=text_score,
        ))

    return results



def _text_overlap(a: str, b: str) -> float:
    """计算两段文本的重叠比例（基于字符集合的 Jaccard 相似度的快速近似）"""
    # 用 n-gram 集合比较，比逐字符更准确
    n = 4
    if len(a) < n or len(b) < n:
        return 0.0
    set_a = set(a[i:i+n] for i in range(len(a) - n + 1))
    set_b = set(b[i:i+n] for i in range(len(b) - n + 1))
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _deduplicate(results: list[SearchResult], threshold: float) -> list[SearchResult]:
    """移除文本高度重叠的搜索结果，保留分数更高的"""
    if threshold <= 0 or threshold > 1:
        return results
    kept: list[SearchResult] = []
    for r in results:
        if any(_text_overlap(r.text, k.text) >= threshold for k in kept):
            continue
        kept.append(r)
    return kept

def hybrid_search(
    db: sqlite3.Connection,
    query_embedding: list[float],
    query_text: str,
    model: str,
    max_results: int = 6,
    min_score: float = 0.35,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    candidate_multiplier: int = 4,
    keyword_query_text: str | None = None,
    dedup_threshold: float = 0.6,
) -> list[SearchResult]:
    """
    混合搜索：向量 + 关键词

    Args:
        db: SQLite 连接
        query_embedding: 查询向量
        query_text: 查询文本
        model: 嵌入模型名称
        max_results: 最大结果数
        min_score: 最小分数阈值
        vector_weight: 向量搜索权重（默认 0.7）
        text_weight: 关键词搜索权重（默认 0.3）
        candidate_multiplier: 候选倍数
        dedup_threshold: 文本去重阈值，重叠比例超过此值则去掉后者

    Returns:
        合并后的搜索结果
    """
    candidates = max_results * candidate_multiplier

    # 1. 向量搜索
    vector_results = search_vector(db, query_embedding, model, candidates)

    # 2. 关键词搜索（支持独立的 keyword query，用于跨语言搜索）
    bm25_query = keyword_query_text or query_text
    # 翻译后的关键词用 OR 连接（不要求全部匹配，匹配越多分越高）
    use_or = keyword_query_text is not None
    keyword_results = search_keyword(db, bm25_query, model, candidates, use_or=use_or)

    # 3. 合并结果
    merged: dict[str, SearchResult] = {}

    # 添加向量结果
    for result in vector_results:
        merged[result.id] = SearchResult(
            id=result.id,
            path=result.path,
            start_line=result.start_line,
            end_line=result.end_line,
            text=result.text,
            score=0.0,
            vector_score=result.vector_score,
            text_score=None,
        )

    # 添加/合并关键词结果
    for result in keyword_results:
        if result.id in merged:
            merged[result.id].text_score = result.text_score
        else:
            merged[result.id] = SearchResult(
                id=result.id,
                path=result.path,
                start_line=result.start_line,
                end_line=result.end_line,
                text=result.text,
                score=0.0,
                vector_score=None,
                text_score=result.text_score,
            )

    # 4. 计算综合分数
    for result in merged.values():
        v_score = result.vector_score or 0.0
        t_score = result.text_score or 0.0
        result.score = vector_weight * v_score + text_weight * t_score

    # 5. 过滤和排序
    final_results = [
        r for r in merged.values()
        if r.score >= min_score
    ]
    final_results.sort(key=lambda x: x.score, reverse=True)

    # 6. 去重：移除文本高度重叠的结果
    final_results = _deduplicate(final_results, dedup_threshold)

    return final_results[:max_results]
