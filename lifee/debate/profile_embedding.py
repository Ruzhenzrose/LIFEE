"""Persona profile embedding - 用一次 query embedding 决定多角色发言顺序

每个角色的 IDENTITY.md 里的 `Role` 字段（例如 Lacan → "Psychoanalyst"）被 embed 成向量，
缓存到 `roles/<name>/profile_embedding.json`（按文本 hash 失效）。

每轮对话时：
1. embed user_query 一次
2. 跟 N 个角色向量做余弦比较
3. 按分降序排（同分随机 tie-break）

这替代了原本每轮跑 N 次 `_search_knowledge`（N 次 embedding + N 次 SQLite 查询）的方案。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Optional

from lifee.memory.embeddings import EmbeddingProvider


_lock = asyncio.Lock()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cache_path(role_dir: Path) -> Path:
    return role_dir / "profile_embedding.json"


def _load_cached(role_dir: Path, source_hash: str, model: str) -> Optional[list[float]]:
    path = _cache_path(role_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("source_hash") != source_hash or data.get("model") != model:
        return None
    vec = data.get("embedding")
    if isinstance(vec, list) and vec:
        return vec
    return None


def _write_cache(role_dir: Path, source_hash: str, source_text: str, embedding: list[float], model: str) -> None:
    payload = {
        "model": model,
        "source_hash": source_hash,
        "source_text": source_text,
        "embedding": embedding,
    }
    _cache_path(role_dir).write_text(json.dumps(payload), encoding="utf-8")


async def _ensure_embeddings(
    entries: list[tuple[str, Optional[Path], str]],
    embedding: EmbeddingProvider,
) -> dict[str, list[float]]:
    """给 [(role_name, role_dir, text), ...] 返回 role_name -> vector。

    - role_dir 为 None 或不存在时不落盘，只算一次就丢
    - 命中缓存的跳过 embed；剩下的一把 embed_batch
    """
    model = embedding.model_name
    result: dict[str, list[float]] = {}
    missing: list[tuple[str, Optional[Path], str, str]] = []

    for name, role_dir, text in entries:
        if not text:
            continue
        h = _hash(text)
        if role_dir is not None and role_dir.exists():
            cached = _load_cached(role_dir, h, model)
            if cached:
                result[name] = cached
                continue
        missing.append((name, role_dir, text, h))

    if missing:
        async with _lock:
            # 再判一次（可能另一协程刚刚写完）
            still_missing = []
            for name, role_dir, text, h in missing:
                if name in result:
                    continue
                if role_dir is not None and role_dir.exists():
                    cached = _load_cached(role_dir, h, model)
                    if cached:
                        result[name] = cached
                        continue
                still_missing.append((name, role_dir, text, h))

            if still_missing:
                texts = [m[2] for m in still_missing]
                try:
                    vectors = await embedding.embed_batch(texts)
                except Exception as e:
                    print(f"[profile_embedding] embed_batch 失败: {type(e).__name__}: {e}")
                    return result
                for (name, role_dir, text, h), vec in zip(still_missing, vectors):
                    result[name] = vec
                    if role_dir is not None and role_dir.exists():
                        try:
                            _write_cache(role_dir, h, text, vec, model)
                        except Exception as e:
                            print(f"[profile_embedding] 写入缓存失败 {name}: {e}")

    return result


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _profile_text(participant) -> str:
    """取角色的 profile 文本。优先 IDENTITY.md 的 Role 字段，fallback 到 display_name。"""
    if getattr(participant, "_custom_soul", None):
        return getattr(participant, "_custom_display_name", "") or ""
    try:
        info = participant.role_manager.get_role_info(participant.role_name)
    except Exception:
        info = {}
    return (info.get("role_tag") or info.get("display_name") or participant.role_name or "").strip()


async def rank_participants(
    participants: list,
    query: str,
    embedding: EmbeddingProvider,
) -> Optional[list]:
    """embed query 一次，按余弦 vs role profile 排序。

    同分随机 tie-break。失败（无可用文本、网络错）时返回 None，由调用方决定是否退回随机。
    """
    if not query or len(participants) <= 1:
        return None

    entries: list[tuple[str, Optional[Path], str]] = []
    for p in participants:
        text = _profile_text(p)
        if not text:
            continue
        role_dir: Optional[Path] = None
        roles_dir = getattr(getattr(p, "role_manager", None), "roles_dir", None)
        if roles_dir is not None:
            candidate = Path(roles_dir) / p.role_name
            if candidate.exists():
                role_dir = candidate
        entries.append((p.role_name, role_dir, text))

    if not entries:
        return None

    role_vectors = await _ensure_embeddings(entries, embedding)
    if not role_vectors:
        return None

    try:
        query_vec = await embedding.embed(query)
    except Exception as e:
        print(f"[profile_embedding] query embed 失败: {type(e).__name__}: {e}")
        return None

    scored: list[tuple[float, object]] = []
    for p in participants:
        vec = role_vectors.get(p.role_name)
        score = _cosine(query_vec, vec) if vec else 0.0
        scored.append((score, p))

    # 先 shuffle 再 stable sort → 同分随机顺序
    random.shuffle(scored)
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def pick_embedding_provider(participants: list) -> Optional[EmbeddingProvider]:
    """从参与者中抽出一个可用的 embedding provider（复用已有的 knowledge_manager）。"""
    for p in participants:
        km = getattr(p, "knowledge_manager", None)
        if km is not None and getattr(km, "embedding", None) is not None:
            return km.embedding
    return None
