"""批量对比角色推荐三种机制

A. LLM(IDs only)        — 当前生产 /recommend-personas，prompt 里只塞 ID 列表
B. LLM(IDs + name + role + voice) — 加料后的 prompt
C. Embedding             — embed(situation) vs embed(SOUL.md head) 取 top-2

跑：
    python scripts/test_persona_recommend.py
环境变量：GOOGLE_API_KEY（用 Gemini 同时跑 LLM 和 embedding）
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

from lifee.memory.embeddings import GeminiEmbedding
from lifee.providers.base import Message, MessageRole

# ---- 10 个角色（前端 ID + 后端 role_name + meta）----
PERSONAS = [
    {"id": "audrey-hepburn", "role_name": "audreyhepburn",
     "name": "AUDREY HEPBURN", "role_label": "ELEGANT MUSE",
     "voice": "Darling, breathe. Ask: what would look simple and honest tomorrow morning?"},
    {"id": "krishnamurti", "role_name": "krishnamurti",
     "name": "Krishnamurti", "role_label": "THE QUESTIONER",
     "voice": "Are you really asking, or seeking confirmation? Don't accept what I say — look for yourself."},
    {"id": "lacan", "role_name": "lacan",
     "name": "Lacan", "role_label": "THE ANALYST",
     "voice": "The unconscious is structured like a language. What slips out when you speak?"},
    {"id": "buffett", "role_name": "buffett",
     "name": "WARREN BUFFETT", "role_label": "VALUE INVESTOR",
     "voice": "You do not need a brilliant move here. You need a sensible one with a margin of safety."},
    {"id": "munger", "role_name": "munger",
     "name": "CHARLIE MUNGER", "role_label": "MENTAL MODELS STRATEGIST",
     "voice": "Try this in reverse: what choice would reliably make your life worse? Eliminate that first."},
    {"id": "drucker", "role_name": "drucker",
     "name": "PETER DRUCKER", "role_label": "MANAGEMENT THINKER",
     "voice": "The right question is 'What needs to be done?' — and where can I contribute?"},
    {"id": "welch", "role_name": "welch",
     "name": "JACK WELCH", "role_label": "CEO / PRACTITIONER",
     "voice": "You can sit here and agonize for six months, or you can make a decision and go."},
    {"id": "shannon", "role_name": "shannon",
     "name": "CLAUDE SHANNON", "role_label": "INFORMATION THEORIST",
     "voice": "How many bits of information do you actually have? Most anxiety is noise vs signal."},
    {"id": "turing", "role_name": "turing",
     "name": "ALAN TURING", "role_label": "FATHER OF COMPUTER SCIENCE",
     "voice": "Can you state the problem precisely enough that a machine could solve it?"},
    {"id": "vonneumann", "role_name": "vonneumann",
     "name": "JOHN VON NEUMANN", "role_label": "POLYMATH",
     "voice": "Model the decision as a game: who are the players, and what is the equilibrium?"},
]

# ---- 15 条覆盖不同场景的测试 situation ----
SITUATIONS = [
    "我最近总是焦虑，晚上失眠，胸口闷",
    "我女朋友要跟我分手，说我们没有未来",
    "我妈妈生病了，我不知道该不该辞职回去陪她",
    "公司这个 PE 40 的科技股值得买吗？",
    "我手上有 50 万存款，想配点资产，怎么分配比较稳",
    "我刚升经理，第一次带 8 个人的团队，不知道怎么开始",
    "我老板让我做一件我觉得不对的事，做还是不做",
    "我准备辞职创业，但太太不支持，怕失败",
    "I keep procrastinating on my dissertation, what should I do",
    "孩子高三了不爱学习只想打游戏，我该怎么办",
    "活着到底是为了什么？最近一直在想这个问题",
    "面试拿了两个 offer，一个钱多一个发展好，怎么选",
    "我总觉得自己不够好，看到别人就自卑",
    "怎么判断我现在的产品方向值不值得继续投入",
    "How do I know if my marriage is worth saving",
]

# ============= Method A: LLM(IDs + full names) — 新版生产 =============
async def method_a(situation: str, personas: list[dict], provider) -> list[str]:
    listing = "\n".join(f"- {p['id']} ({p['name']})" for p in personas)
    prompt = (
        "You are a persona recommendation engine for a life-coaching debate app.\n\n"
        f"User's situation:\n{situation.strip()}\n\n"
        "Life context tags: none\n\n"
        f"Available personas (id and full name):\n{listing}\n\n"
        "Select exactly 2 persona IDs that would resonate most with this user's situation. "
        "Prioritise emotional fit first, then intellectual fit. "
        "Only use IDs from the list above. "
        'Reply ONLY with a JSON array of exactly 2 items, e.g. ["buffett","krishnamurti"]'
    )
    msgs = [Message(role=MessageRole.USER, content=prompt)]
    chunks = []
    async for chunk in provider.stream(messages=msgs, max_tokens=40, temperature=0.3):
        chunks.append(chunk)
    text = "".join(chunks).strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1).strip()
    try:
        ids = json.loads(text)
        valid_ids = {p["id"] for p in personas}
        return [i for i in ids if i in valid_ids][:2]
    except Exception:
        return []

# ============= Method B: LLM(IDs + name + role + voice) =============
async def method_b(situation: str, personas: list[dict], provider) -> list[str]:
    persona_lines = "\n".join(
        f"- {p['id']} ({p['name']}, {p['role_label']}): \"{p['voice']}\""
        for p in personas
    )
    prompt = (
        "You are a persona recommendation engine for a life-coaching debate app.\n\n"
        f"User's situation:\n{situation.strip()}\n\n"
        "Life context tags: none\n\n"
        f"Available personas:\n{persona_lines}\n\n"
        "Select exactly 2 persona IDs whose framing and voice would resonate most with this user. "
        "Prioritise emotional fit first, then intellectual fit. Match the angle each persona is set up for, "
        "not just the person's general fame. Only use IDs from the list above. "
        'Reply ONLY with a JSON array of exactly 2 items, e.g. ["buffett","krishnamurti"]'
    )
    msgs = [Message(role=MessageRole.USER, content=prompt)]
    chunks = []
    async for chunk in provider.stream(messages=msgs, max_tokens=40, temperature=0.3):
        chunks.append(chunk)
    text = "".join(chunks).strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1).strip()
    try:
        ids = json.loads(text)
        valid_ids = {p["id"] for p in personas}
        return [i for i in ids if i in valid_ids][:2]
    except Exception:
        return []

# ============= Method C: Embedding =============
def _soul_head(role_name: str) -> str:
    """SOUL.md 头部（标题 + 引言 + 第一个 ## 段）"""
    role_dir = REPO / "lifee" / "roles" / role_name
    for soul_name in ("SOUL.md", "soul.md", "Soul.md"):
        p = role_dir / soul_name
        if p.exists():
            full = p.read_text(encoding="utf-8")
            lines = full.split("\n")
            h2_count = 0
            kept = []
            for line in lines:
                if line.lstrip().startswith("## "):
                    h2_count += 1
                    if h2_count >= 2:
                        break
                kept.append(line)
            return "\n".join(kept).strip()
    return ""

def _cosine(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

async def method_c(situation: str, personas: list[dict],
                   embedding: GeminiEmbedding,
                   role_vecs: dict[str, list[float]]) -> list[tuple[str, float]]:
    q_vec = await embedding.embed(situation)
    scored = []
    for p in personas:
        vec = role_vecs.get(p["role_name"])
        score = _cosine(q_vec, vec) if vec else 0.0
        scored.append((p["id"], score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:2]

# ============= Main =============
async def main():
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        print("缺 GOOGLE_API_KEY")
        return

    # provider for LLM
    provider_name = (os.getenv("API_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "gemini").lower()
    if provider_name == "gemini":
        from lifee.providers import GeminiProvider
        provider = GeminiProvider(api_key=key, model=os.getenv("LLM_MODEL") or "gemini-2.0-flash")
    elif provider_name == "deepseek":
        from lifee.providers.openai_compat import DeepSeekProvider
        provider = DeepSeekProvider(api_key=os.getenv("DEEPSEEK_API_KEY"), model="deepseek-chat")
    else:
        from lifee.providers import GeminiProvider
        provider = GeminiProvider(api_key=key, model="gemini-2.0-flash")
    print(f"LLM provider: {provider_name}")

    # embedding + 预算所有角色的 soul-head 向量
    embedding = GeminiEmbedding(api_key=key)
    print("预计算 SOUL embedding ...")
    soul_texts = []
    role_names = []
    for p in PERSONAS:
        head = _soul_head(p["role_name"])
        if not head:
            print(f"  ⚠ {p['role_name']} 没有 SOUL.md，跳过")
            continue
        soul_texts.append(head)
        role_names.append(p["role_name"])
    soul_vecs = await embedding.embed_batch(soul_texts)
    role_vecs = dict(zip(role_names, soul_vecs))
    print(f"  完成（{len(role_vecs)} 个）\n")

    # 跑 + 收集
    rows = []
    for i, sit in enumerate(SITUATIONS, 1):
        print(f"[{i}/{len(SITUATIONS)}] {sit}")
        try:
            t0 = time.time()
            a = await method_a(sit, PERSONAS, provider)
            ta = (time.time() - t0) * 1000
        except Exception as e:
            a, ta = [f"ERR:{e}"], 0
        try:
            t0 = time.time()
            b = await method_b(sit, PERSONAS, provider)
            tb = (time.time() - t0) * 1000
        except Exception as e:
            b, tb = [f"ERR:{e}"], 0
        try:
            t0 = time.time()
            c_scored = await method_c(sit, PERSONAS, embedding, role_vecs)
            c = [f"{cid}({score:.2f})" for cid, score in c_scored]
            tc = (time.time() - t0) * 1000
        except Exception as e:
            c, tc = [f"ERR:{e}"], 0

        print(f"  A (IDs only,    {ta:5.0f}ms): {a}")
        print(f"  B (IDs+meta,    {tb:5.0f}ms): {b}")
        print(f"  C (embedding,   {tc:5.0f}ms): {c}")
        print()

        rows.append({"situation": sit, "A": a, "B": b, "C": c_scored if isinstance(c_scored, list) else [],
                     "ta_ms": int(ta), "tb_ms": int(tb), "tc_ms": int(tc)})

    # ---- 汇总：A vs B / A vs C / B vs C 的重合率 ----
    def overlap(x, y):
        sx, sy = set(x), set(y)
        return len(sx & sy)

    print("=" * 80)
    print("汇总（top-2 重合数 / 2）")
    print("=" * 80)
    print(f"{'#':<3}{'situation':<55}{'A∩B':<6}{'A∩C':<6}{'B∩C':<6}")
    for i, r in enumerate(rows, 1):
        a, b = r["A"], r["B"]
        c_ids = [cid for cid, _ in r["C"]]
        sit = r["situation"][:52]
        print(f"{i:<3}{sit:<55}{overlap(a,b):<6}{overlap(a,c_ids):<6}{overlap(b,c_ids):<6}")

    avg_ab = sum(overlap(r["A"], r["B"]) for r in rows) / len(rows)
    avg_ac = sum(overlap(r["A"], [cid for cid, _ in r["C"]]) for r in rows) / len(rows)
    avg_bc = sum(overlap(r["B"], [cid for cid, _ in r["C"]]) for r in rows) / len(rows)
    print(f"\n平均重合（满分 2）: A∩B={avg_ab:.2f}  A∩C={avg_ac:.2f}  B∩C={avg_bc:.2f}")

    avg_ta = sum(r["ta_ms"] for r in rows) / len(rows)
    avg_tb = sum(r["tb_ms"] for r in rows) / len(rows)
    avg_tc = sum(r["tc_ms"] for r in rows) / len(rows)
    print(f"平均耗时 (ms)     : A={avg_ta:.0f}  B={avg_tb:.0f}  C={avg_tc:.0f}")

    # 写到 json，方便后续人工标注
    out = REPO / "scripts" / "test_persona_recommend_results.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果写到：{out}")


if __name__ == "__main__":
    asyncio.run(main())
