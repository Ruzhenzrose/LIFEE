"""离线验证 profile_embedding.rank_participants

用真实的 Gemini API，为几个典型 query 排 LIFEE 里差异明显的角色：
- lacan (Psychoanalyst)
- buffett (Investor)
- turing (Mathematician)
- krishnamurti (Speaker in dialogue)
- drucker (Management thinker)

验证：
1. 能成功建 embedding、写缓存
2. 排序在常识上合不合理
3. 第二次跑同一 query 时能命中缓存（只 embed query，不 embed role）
"""
from __future__ import annotations
import asyncio
import os
import sys
import time
from pathlib import Path

# 确保 import 路径 = 项目根
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from lifee.debate.profile_embedding import rank_participants
from lifee.memory.embeddings import GeminiEmbedding
from lifee.roles import RoleManager


class FakeParticipant:
    """最小壳，rank_participants 只依赖 role_name / role_manager / _custom_soul 几项"""
    def __init__(self, role_name: str, role_manager: RoleManager):
        self.role_name = role_name
        self.role_manager = role_manager
        self._custom_soul = None
        self._custom_display_name = None
        self.knowledge_manager = None

        class _Info:
            def __init__(self, name):
                self.name = name
                self.display_name = name
        self.info = _Info(role_name)


async def main():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        print("缺 GOOGLE_API_KEY")
        return
    emb = GeminiEmbedding(api_key=key)
    rm = RoleManager(REPO / "lifee" / "roles")

    role_names = ["lacan", "buffett", "turing", "krishnamurti", "drucker"]
    participants = [FakeParticipant(r, rm) for r in role_names]

    # 先打印每个角色的 profile 文本
    print("=== role_tag ===")
    for p in participants:
        info = rm.get_role_info(p.role_name)
        print(f"  {p.role_name:25} role_tag = {info.get('role_tag')!r}")
    print()

    queries = [
        "我最近总是焦虑，晚上失眠",
        "这家公司 PE 40 值得买吗？",
        "How does a Turing machine handle halting?",
        "我女朋友要跟我分手",
        "怎样带好一个十人团队",
        "生命的意义是什么",
    ]

    for q in queries:
        t0 = time.time()
        sorted_p = await rank_participants(participants, q, emb)
        dt = (time.time() - t0) * 1000
        print(f"[{dt:6.0f} ms] {q}")
        if sorted_p is None:
            print("  → rank 失败")
            continue
        for i, p in enumerate(sorted_p):
            print(f"  {i+1}. {p.role_name}")
        print()

    # 再跑一遍同一 query，测缓存命中速度
    q = queries[0]
    t0 = time.time()
    await rank_participants(participants, q, emb)
    dt = (time.time() - t0) * 1000
    print(f"[缓存复跑] {dt:.0f} ms  (应该只剩 1 次 query embed)")


if __name__ == "__main__":
    asyncio.run(main())
