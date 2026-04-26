"""测试 /generate-personas 新 prompt（带 roster + 删除 non-obvious 要求）

跑：
    python scripts/test_persona_generate.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from fastapi.testclient import TestClient

# 直接调用 endpoint（不走 HTTP server）
ROSTER = [
    {"id": "audrey-hepburn", "name": "Audrey Hepburn", "role": "ELEGANT MUSE"},
    {"id": "krishnamurti",   "name": "Krishnamurti",   "role": "THE QUESTIONER"},
    {"id": "lacan",          "name": "Lacan",          "role": "THE ANALYST"},
    {"id": "buffett",        "name": "Warren Buffett", "role": "VALUE INVESTOR"},
    {"id": "munger",         "name": "Charlie Munger", "role": "MENTAL MODELS STRATEGIST"},
    {"id": "drucker",        "name": "Peter Drucker",  "role": "MANAGEMENT THINKER"},
    {"id": "welch",          "name": "Jack Welch",     "role": "CEO / PRACTITIONER"},
    {"id": "shannon",        "name": "Claude Shannon", "role": "INFORMATION THEORIST"},
    {"id": "turing",         "name": "Alan Turing",    "role": "FATHER OF COMPUTER SCIENCE"},
    {"id": "vonneumann",     "name": "John von Neumann","role": "POLYMATH"},
]

SITUATIONS = [
    "我妈妈生病了，我不知道该不该辞职回去陪她",
    "我女朋友要跟我分手，说我们没有未来",
    "孩子高三了不爱学习只想打游戏",
    "活着到底是为了什么？",
    "How do I know if my marriage is worth saving",
    "我准备辞职创业，但太太不支持",
    "我老板让我做一件我觉得不对的事",
    "我总觉得自己不够好",
]


async def main():
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("DEEPSEEK_API_KEY"):
        print("缺 API key (GOOGLE_API_KEY 或 DEEPSEEK_API_KEY)")
        return

    # 直接拿到 endpoint handler
    from lifee.api import app

    client = TestClient(app)

    # 先看下 roster 在 prompt 里长什么样（dry-run 调一次，打印失败也无所谓）
    for i, sit in enumerate(SITUATIONS, 1):
        print(f"\n[{i}/{len(SITUATIONS)}] {sit}")
        t0 = time.time()
        resp = client.post(
            "/generate-personas",
            json={
                "situation": sit,
                "periods": [],
                "existing_ids": [],
                "roster": ROSTER,
            },
        )
        dt = (time.time() - t0) * 1000
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            continue
        data = resp.json()
        personas = data.get("personas", [])
        if not personas:
            print(f"  ⚠ 没生成出来 ({dt:.0f}ms)：{data.get('error', '')}")
            continue
        print(f"  ({dt:.0f}ms)")
        roster_ids = {r["id"] for r in ROSTER}
        roster_names = {r["name"].lower() for r in ROSTER}
        for j, p in enumerate(personas, 1):
            name = p.get("name", "")
            role = p.get("role", "")
            voice = p.get("voice", "")
            soul_len = len(p.get("soul", ""))
            # 检测是否撞名册
            collide = ""
            if name.lower() in roster_names:
                collide = "  ⚠ 撞名册"
            elif p.get("id", "").replace("gen-", "") in roster_ids:
                collide = "  ⚠ ID 撞名册"
            print(f"    {j}. {name}  ({role}){collide}")
            print(f"       voice: {voice[:90]}")
            print(f"       soul:  {soul_len} chars")


if __name__ == "__main__":
    asyncio.run(main())
