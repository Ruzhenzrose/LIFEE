"""只读：扫 Supabase 里引用已删除 persona 的孤儿记录，报数量，不动数据。"""
import os
import sys
import json
import httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEAD_IDS = [
    "positive_psychologist", "caretaker",
    "enterprise", "serene", "architect", "rebel", "tarot-master",
    "lifecoach",  # 旧别名
]

URL = os.environ["SUPABASE_URL"].strip('"')
KEY = os.environ["SUPABASE_KEY"].strip('"')
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}


def get(path, params=None, prefer=None):
    headers = dict(H)
    if prefer:
        headers["Prefer"] = prefer
    r = httpx.get(f"{URL}/rest/v1/{path}", headers=headers, params=params, timeout=20)
    r.raise_for_status()
    return r


def count(path, params=None):
    r = get(path, params, prefer="count=exact")
    cr = r.headers.get("content-range", "")
    return int(cr.split("/")[-1]) if "/" in cr else len(r.json())


print(f"扫描目标 IDs: {DEAD_IDS}\n")

print("=== chat_messages（按 persona_id 计） ===")
total_msg = 0
for pid in DEAD_IDS:
    n = count("chat_messages", {"persona_id": f"eq.{pid}", "select": "id"})
    if n > 0:
        print(f"  {pid:28} {n:6d} rows")
        total_msg += n
print(f"  -- total dead messages: {total_msg}")

print("\n=== chat_sessions（personas 数组含任一 dead id） ===")
total_sess = 0
per_id = {}
for pid in DEAD_IDS:
    # PostgREST: personas::jsonb @> '["id"]'
    n = count("chat_sessions", {
        "personas": f"cs.[\"{pid}\"]",
        "select": "id",
    })
    if n > 0:
        per_id[pid] = n
        print(f"  含 {pid:28} {n:6d} sessions")
        total_sess += n

print(f"\n=== 纯孤儿 session：personas 全部是 dead id（最惨的情况，该整条删） ===")
# 获取所有含任一 dead id 的 session，然后在本地判断 personas 是否全是 dead id
if per_id:
    all_dead_ids_or = ",".join([f"personas.cs.[\"{pid}\"]" for pid in per_id.keys()])
    r = get("chat_sessions", {
        "or": f"({all_dead_ids_or})",
        "select": "id,personas,user_id,updated_at",
        "limit": "10000",
    })
    rows = r.json()
    pure = [r for r in rows if r.get("personas") and all(p in DEAD_IDS for p in r["personas"])]
    print(f"  纯孤儿 session 数: {len(pure)}")
    if pure[:5]:
        print(f"  样例（前 5）:")
        for s in pure[:5]:
            print(f"    id={s['id']}  personas={s['personas']}  updated={s.get('updated_at')}")

print("\n只读扫描结束，未动任何数据。")
