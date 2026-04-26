"""对比 /generate-personas 在有/无 web search 时的输出

跑：
    python scripts/test_persona_generate_websearch.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from fastapi.testclient import TestClient

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
    "我老板让我做一件我觉得不对的事",
    "我总觉得自己不够好",
]


def _call(client, situation, use_search):
    t0 = time.time()
    resp = client.post(
        "/generate-personas",
        json={
            "situation": situation,
            "periods": [],
            "existing_ids": [],
            "roster": ROSTER,
            "use_web_search": use_search,
        },
    )
    dt = (time.time() - t0) * 1000
    if resp.status_code != 200:
        return None, dt, f"HTTP {resp.status_code}"
    data = resp.json()
    personas = data.get("personas", [])
    return personas, dt, data.get("error", "")


def _fmt(personas):
    if not personas:
        return ["  (空)"]
    out = []
    for p in personas:
        out.append(f"  • {p.get('name','')} ({p.get('role','')})")
        v = p.get("voice", "")
        out.append(f"    voice: {v[:90]}")
    return out


async def main():
    if not os.getenv("GOOGLE_API_KEY"):
        print("缺 GOOGLE_API_KEY（web_search 需要）")
        return

    from lifee.api import app
    client = TestClient(app)

    rows = []
    for i, sit in enumerate(SITUATIONS, 1):
        print(f"\n[{i}/{len(SITUATIONS)}] {sit}")

        print("  -- 不带 web search --")
        a, ta, ea = _call(client, sit, use_search=False)
        for line in _fmt(a):
            print(line)
        print(f"    ({ta:.0f} ms){' err='+ea if ea else ''}")

        print("  -- 带 web search --")
        b, tb, eb = _call(client, sit, use_search=True)
        for line in _fmt(b):
            print(line)
        print(f"    ({tb:.0f} ms){' err='+eb if eb else ''}")

        rows.append({"situation": sit, "no_search": a, "with_search": b, "ta": ta, "tb": tb})

    # 汇总
    print("\n" + "=" * 80)
    print("汇总")
    print("=" * 80)
    print(f"{'#':<3}{'situation':<40}{'A 选人 (no search)':<40}{'B 选人 (web search)':<40}")
    for i, r in enumerate(rows, 1):
        a_names = "/".join((p.get("name", "")[:18] for p in (r["no_search"] or []))) or "—"
        b_names = "/".join((p.get("name", "")[:18] for p in (r["with_search"] or []))) or "—"
        sit = r["situation"][:38]
        print(f"{i:<3}{sit:<40}{a_names:<40}{b_names:<40}")

    avg_a = sum(r["ta"] for r in rows) / len(rows)
    avg_b = sum(r["tb"] for r in rows) / len(rows)
    print(f"\n平均耗时: 不带 search {avg_a:.0f} ms  带 search {avg_b:.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
