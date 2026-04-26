"""诊断：Viktor Frankl 高频出现是 LLM 先验，还是别的问题

三个对照实验：
1. 同一 situation 跑 5 次（temperature=0.8 应该有变化）→ 看 Frankl 出现频率
2. 完全跟人生意义无关的 situation（如修汽车）→ 看 Frankl 还会不会出现
3. prompt 里显式禁止 Frankl → 看他能不能消失
"""
from __future__ import annotations
import os, sys, time
from collections import Counter
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


def call(client, situation):
    r = client.post("/generate-personas", json={
        "situation": situation, "periods": [], "existing_ids": [],
        "roster": ROSTER, "use_web_search": False,
    })
    if r.status_code != 200:
        return []
    return r.json().get("personas", []) or []


def names(personas):
    return [p.get("name", "") for p in personas]


def main():
    from lifee.api import app
    client = TestClient(app)

    print("=" * 70)
    print("实验 1：同一 situation 跑 5 次（'我妈妈生病了'）")
    print("temperature=0.8 应该有变化；如果 Frankl 5/5 → 极强先验")
    print("=" * 70)
    counter = Counter()
    for i in range(5):
        t0 = time.time()
        ps = call(client, "我妈妈生病了，我不知道该不该辞职回去陪她")
        ns = names(ps)
        for n in ns:
            counter[n] += 1
        print(f"  run {i+1} ({(time.time()-t0)*1000:.0f}ms): {ns}")
    print(f"\n  汇总（10 个 slot）: {counter.most_common()}")

    print("\n" + "=" * 70)
    print("实验 2：跟人生意义/苦难毫无关系的 situation")
    print("如果 Frankl 还出现，那 LLM 是无脑塞他；否则就是情境触发的先验")
    print("=" * 70)
    off_topic = [
        "我家电脑显卡风扇响，是不是要换了",
        "想学做川菜但不会切菜，从哪本菜谱开始",
        "厨房地砖该选 600x600 还是 800x800",
        "我家狗子最近老挠耳朵，是不是耳螨",
    ]
    for sit in off_topic:
        ps = call(client, sit)
        ns = names(ps)
        marker = "  ⚠ FRANKL!" if any("frankl" in n.lower() for n in ns) else ""
        print(f"  '{sit}'\n    → {ns}{marker}")

    print("\n" + "=" * 70)
    print("实验 3：roster 里加上 Frankl，看 LLM 是否还能避开他")
    print("如果还选他 → 不听指令；如果换人 → 他只是 top-1 默认")
    print("=" * 70)
    roster_with_frankl = ROSTER + [
        {"id": "frankl", "name": "Viktor Frankl", "role": "LOGOTHERAPIST"},
    ]
    for i in range(3):
        r = client.post("/generate-personas", json={
            "situation": "我女朋友要跟我分手",
            "periods": [], "existing_ids": [], "roster": roster_with_frankl,
            "use_web_search": False,
        })
        if r.status_code == 200:
            ps = r.json().get("personas", []) or []
            ns = names(ps)
            marker = "  ⚠ 违反指令" if any("frankl" in n.lower() for n in ns) else ""
            print(f"  run {i+1}: {ns}{marker}")


if __name__ == "__main__":
    main()
