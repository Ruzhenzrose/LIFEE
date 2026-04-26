"""LIFEE 本地存储层 —— SQLite。

替换掉原来 api.py 里 100+ 处直接打 Supabase REST 的代码。所有函数都是同步，
在 FastAPI 异步路由里用 `await asyncio.to_thread(store.xxx, ...)` 调用即可；
SQLite 本身走文件 IO 很快，不值得再引一个 aiosqlite 依赖。

环境变量：
  LIFEE_DB_PATH   — SQLite 文件位置，默认 <项目根>/data/lifee.db
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

# --------------------------------------------------------------------------- #
# 连接管理
# --------------------------------------------------------------------------- #

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = Path(os.getenv("LIFEE_DB_PATH") or (_ROOT / "data" / "lifee.db"))

_conn_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """懒初始化单一共享连接 + WAL 模式。check_same_thread=False 让 to_thread 池的
    各线程共用同一个连接；SQLite 本身已经 thread-safe（serialized mode 默认）。"""
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(
            str(_DB_PATH),
            check_same_thread=False,
            isolation_level=None,  # autocommit；事务显式用 BEGIN/COMMIT
            timeout=30.0,
        )
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=5000")
        _conn = c
        _init_schema(c)
        return c


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
    user_memory TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS email_otps (
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    purpose TEXT NOT NULL,        -- 'signup' | 'reset'
    expires_at INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (email, code, purpose)
);
CREATE INDEX IF NOT EXISTS idx_otp_email ON email_otps(email, purpose);

CREATE TABLE IF NOT EXISTS user_credits (
    uid TEXT PRIMARY KEY,          -- 'user:<id>' 或 guest uuid
    balance INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ct_uid ON credit_transactions(uid, created_at DESC);

CREATE TABLE IF NOT EXISTS redeem_codes (
    code TEXT PRIMARY KEY,
    credits INTEGER NOT NULL,
    used_by TEXT,
    used_at INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    personas TEXT NOT NULL DEFAULT '[]',           -- JSON array
    starred INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    last_options TEXT NOT NULL DEFAULT '{}',       -- JSON
    last_extract_msg_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cs_user ON chat_sessions(user_id, deleted, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    persona_id TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE(session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_cm_session ON chat_messages(session_id, seq);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    content TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


def _init_schema(c: sqlite3.Connection) -> None:
    c.executescript(_SCHEMA)
    # 迁移：老 db 没有 display_name / avatar_url 列时补上
    cols = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
    if "display_name" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    if "avatar_url" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT NOT NULL DEFAULT ''")


def now() -> int:
    return int(time.time())


# --------------------------------------------------------------------------- #
# Users / Auth
# --------------------------------------------------------------------------- #


def user_by_email(email: str) -> dict | None:
    r = _get_conn().execute("SELECT * FROM users WHERE email=? LIMIT 1", (email.lower(),)).fetchone()
    return dict(r) if r else None


def user_by_id(user_id: str) -> dict | None:
    r = _get_conn().execute("SELECT * FROM users WHERE id=? LIMIT 1", (user_id,)).fetchone()
    return dict(r) if r else None


def user_create(email: str, password_hash: str) -> str:
    """创建用户（email_verified=0），返回 user_id。email 冲突抛 ValueError。"""
    uid = str(uuid4())
    try:
        _get_conn().execute(
            "INSERT INTO users (id, email, password_hash, email_verified, created_at) VALUES (?, ?, ?, 0, ?)",
            (uid, email.lower(), password_hash, now()),
        )
    except sqlite3.IntegrityError:
        raise ValueError("email_already_exists")
    return uid


def user_set_verified(user_id: str) -> None:
    _get_conn().execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))


def user_set_password(user_id: str, password_hash: str) -> None:
    _get_conn().execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))


def user_get_memory(user_id: str) -> str:
    r = _get_conn().execute("SELECT user_memory FROM users WHERE id=?", (user_id,)).fetchone()
    return r["user_memory"] if r else ""


def user_set_memory(user_id: str, memory: str) -> None:
    _get_conn().execute("UPDATE users SET user_memory=? WHERE id=?", (memory, user_id))


def user_get_name(user_id: str) -> str:
    r = _get_conn().execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()
    return (r["display_name"] if r else "") or ""


def user_set_name(user_id: str, name: str) -> None:
    _get_conn().execute("UPDATE users SET display_name=? WHERE id=?", ((name or "")[:80], user_id))


def user_get_avatar(user_id: str) -> str:
    r = _get_conn().execute("SELECT avatar_url FROM users WHERE id=?", (user_id,)).fetchone()
    return (r["avatar_url"] if r else "") or ""


def user_set_avatar(user_id: str, avatar_url: str) -> None:
    # data:image base64 头像可能超大，截到 ~200KB（够 256x256 webp 高质量）
    _get_conn().execute("UPDATE users SET avatar_url=? WHERE id=?", ((avatar_url or "")[:200_000], user_id))


# --------------------------------------------------------------------------- #
# Email OTP
# --------------------------------------------------------------------------- #


def otp_create(email: str, purpose: str, ttl_seconds: int = 600) -> str:
    """生成 6 位 OTP，写入 email_otps。同一邮箱旧 OTP 先清掉。"""
    code = f"{secrets.randbelow(1_000_000):06d}"
    ts = now()
    with _get_conn() as c:
        c.execute("DELETE FROM email_otps WHERE email=? AND purpose=?", (email.lower(), purpose))
        c.execute(
            "INSERT INTO email_otps (email, code, purpose, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (email.lower(), code, purpose, ts + ttl_seconds, ts),
        )
    return code


def otp_consume(email: str, code: str, purpose: str) -> bool:
    """校验并一次性消耗 OTP。过期的同时清理。"""
    c = _get_conn()
    ts = now()
    c.execute("DELETE FROM email_otps WHERE expires_at < ?", (ts,))
    r = c.execute(
        "SELECT 1 FROM email_otps WHERE email=? AND code=? AND purpose=? AND expires_at >= ?",
        (email.lower(), code, purpose, ts),
    ).fetchone()
    if not r:
        return False
    c.execute(
        "DELETE FROM email_otps WHERE email=? AND code=? AND purpose=?",
        (email.lower(), code, purpose),
    )
    return True


# --------------------------------------------------------------------------- #
# Credits
# --------------------------------------------------------------------------- #


def credits_get(uid: str) -> int | None:
    """返回当前余额；记录不存在返回 None（让调用方决定要不要初始化）。"""
    r = _get_conn().execute("SELECT balance FROM user_credits WHERE uid=?", (uid,)).fetchone()
    return int(r["balance"]) if r else None


def credits_ensure(uid: str, initial: int) -> int:
    """读余额；没记录就按 initial 建一条。返回最终余额。"""
    c = _get_conn()
    r = c.execute("SELECT balance FROM user_credits WHERE uid=?", (uid,)).fetchone()
    if r:
        return int(r["balance"])
    c.execute(
        "INSERT OR IGNORE INTO user_credits (uid, balance, updated_at) VALUES (?, ?, ?)",
        (uid, initial, now()),
    )
    # 竞态：上面 OR IGNORE 可能因为另一线程刚插入而被忽略，再读一次
    r = c.execute("SELECT balance FROM user_credits WHERE uid=?", (uid,)).fetchone()
    return int(r["balance"]) if r else initial


def credits_set(uid: str, balance: int) -> None:
    _get_conn().execute(
        "INSERT INTO user_credits (uid, balance, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(uid) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at",
        (uid, balance, now()),
    )


def credits_debit(uid: str, amount: int = 1, reason: str = "chat") -> bool:
    """原子扣款，余额不足返回 False。"""
    c = _get_conn()
    with c:  # 显式事务
        r = c.execute("SELECT balance FROM user_credits WHERE uid=?", (uid,)).fetchone()
        if not r or int(r["balance"]) < amount:
            return False
        c.execute(
            "UPDATE user_credits SET balance=balance-?, updated_at=? WHERE uid=?",
            (amount, now(), uid),
        )
        c.execute(
            "INSERT INTO credit_transactions (uid, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (uid, -amount, reason, now()),
        )
    return True


def credits_migrate(from_uid: str, to_uid: str) -> None:
    """把 from_uid 的余额合并到 to_uid。失败静默。"""
    if not from_uid or from_uid == to_uid:
        return
    c = _get_conn()
    with c:
        r1 = c.execute("SELECT balance FROM user_credits WHERE uid=?", (from_uid,)).fetchone()
        if not r1:
            return
        from_bal = int(r1["balance"])
        r2 = c.execute("SELECT balance FROM user_credits WHERE uid=?", (to_uid,)).fetchone()
        to_bal = int(r2["balance"]) if r2 else 0
        c.execute(
            "INSERT INTO user_credits (uid, balance, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at",
            (to_uid, from_bal + to_bal, now()),
        )
        c.execute("DELETE FROM user_credits WHERE uid=?", (from_uid,))


def credits_log(uid: str, amount: int, reason: str) -> None:
    """纯日志（不改余额），用于 chat 日志之类。"""
    _get_conn().execute(
        "INSERT INTO credit_transactions (uid, amount, reason, created_at) VALUES (?, ?, ?, ?)",
        (uid, amount, reason, now()),
    )


# --------------------------------------------------------------------------- #
# Redeem codes
# --------------------------------------------------------------------------- #


def redeem_codes_bulk_insert(rows: list[tuple[str, int]]) -> None:
    """rows: [(code, credits), ...]"""
    ts = now()
    with _get_conn() as c:
        c.executemany(
            "INSERT OR IGNORE INTO redeem_codes (code, credits, created_at) VALUES (?, ?, ?)",
            [(code, credits, ts) for code, credits in rows],
        )


def redeem_use(code: str, uid: str) -> tuple[bool, str, int]:
    """
    消耗兑换码 + 加余额 + 记流水。返回 (ok, message, 本次充值面额)。
    """
    code = code.strip().upper()
    c = _get_conn()
    with c:
        r = c.execute(
            "SELECT credits FROM redeem_codes WHERE code=? AND used_by IS NULL",
            (code,),
        ).fetchone()
        if not r:
            return (False, "invalid or used", 0)
        credits_amt = int(r["credits"])
        ts = now()
        c.execute(
            "UPDATE redeem_codes SET used_by=?, used_at=? WHERE code=? AND used_by IS NULL",
            (uid, ts, code),
        )
        if c.total_changes == 0:
            return (False, "already used", 0)
        # 加余额（用 ON CONFLICT UPSERT，兼容首次兑换的新 uid）
        cur = c.execute("SELECT balance FROM user_credits WHERE uid=?", (uid,)).fetchone()
        new_bal = (int(cur["balance"]) if cur else 0) + credits_amt
        c.execute(
            "INSERT INTO user_credits (uid, balance, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at",
            (uid, new_bal, ts),
        )
        c.execute(
            "INSERT INTO credit_transactions (uid, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (uid, credits_amt, f"redeem:{code}", ts),
        )
    return (True, f"+{credits_amt} credits", credits_amt)


# --------------------------------------------------------------------------- #
# Chat sessions
# --------------------------------------------------------------------------- #


def session_exists(session_id: str) -> bool:
    r = _get_conn().execute(
        "SELECT 1 FROM chat_sessions WHERE id=? AND deleted=0", (session_id,)
    ).fetchone()
    return r is not None


def session_get(session_id: str) -> dict | None:
    r = _get_conn().execute(
        "SELECT * FROM chat_sessions WHERE id=? AND deleted=0", (session_id,)
    ).fetchone()
    if not r:
        return None
    d = dict(r)
    d["personas"] = json.loads(d.get("personas") or "[]")
    d["last_options"] = json.loads(d.get("last_options") or "{}")
    return d


def session_ensure(
    session_id: str,
    user_id: str,
    *,
    title: str = "",
    personas: list | None = None,
    last_options: dict | None = None,
) -> bool:
    """存在就返回 False；不存在就新建返回 True。"""
    c = _get_conn()
    r = c.execute("SELECT 1 FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
    if r:
        return False
    ts = now()
    c.execute(
        "INSERT INTO chat_sessions (id, user_id, title, personas, last_options, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            user_id,
            title,
            json.dumps(personas or []),
            json.dumps(last_options or {}),
            ts,
            ts,
        ),
    )
    return True


def session_update(session_id: str, **fields: Any) -> None:
    """
    允许更新的字段：title, personas, starred, deleted, last_options,
    last_extract_msg_count。updated_at 自动更新。
    """
    allowed = {
        "title", "personas", "starred", "deleted",
        "last_options", "last_extract_msg_count",
    }
    updates: dict[str, Any] = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("personas", "last_options") and not isinstance(v, str):
            v = json.dumps(v)
        elif k in ("starred", "deleted"):
            v = 1 if v else 0
        updates[k] = v
    if not updates:
        return
    updates["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in updates)
    _get_conn().execute(
        f"UPDATE chat_sessions SET {cols} WHERE id=?",
        (*updates.values(), session_id),
    )


def session_list(user_id: str, limit: int = 20) -> list[dict]:
    rows = _get_conn().execute(
        "SELECT cs.id, cs.title, cs.personas, cs.starred, cs.updated_at, "
        "       (SELECT COUNT(*) FROM chat_messages cm WHERE cm.session_id=cs.id) AS message_count "
        "FROM chat_sessions cs "
        "WHERE cs.user_id=? AND cs.deleted=0 "
        "ORDER BY cs.updated_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["personas"] = json.loads(d.get("personas") or "[]")
        out.append(d)
    return out


def session_soft_delete(session_id: str, user_id: str) -> bool:
    c = _get_conn()
    c.execute(
        "UPDATE chat_sessions SET deleted=1, updated_at=? WHERE id=? AND user_id=?",
        (now(), session_id, user_id),
    )
    return c.total_changes > 0


# --------------------------------------------------------------------------- #
# Chat messages
# --------------------------------------------------------------------------- #


def msg_save(
    session_id: str,
    role: str,
    content: str,
    *,
    seq: int | None = None,
    persona_id: str | None = None,
) -> int:
    """返回 seq。seq=None 时自动 max(seq)+1。"""
    c = _get_conn()
    with c:
        if seq is None:
            r = c.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS next_seq FROM chat_messages WHERE session_id=?",
                (session_id,),
            ).fetchone()
            seq = int(r["next_seq"])
        c.execute(
            "INSERT OR REPLACE INTO chat_messages "
            "(session_id, seq, role, content, persona_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, seq, role, content, persona_id, now()),
        )
        c.execute(
            "UPDATE chat_sessions SET updated_at=? WHERE id=?",
            (now(), session_id),
        )
    return seq


def msg_update_content(session_id: str, seq: int, content: str) -> None:
    """只改 content，保留 persona_id / role / created_at。
    流式生成中每个 token 到达都会调这个，不能用 INSERT OR REPLACE（会把 persona_id 清掉）。"""
    _get_conn().execute(
        "UPDATE chat_messages SET content=? WHERE session_id=? AND seq=?",
        (content, session_id, seq),
    )


def msg_next_seq(session_id: str) -> int:
    r = _get_conn().execute(
        "SELECT COALESCE(MAX(seq), -1) + 1 AS next_seq FROM chat_messages WHERE session_id=?",
        (session_id,),
    ).fetchone()
    return int(r["next_seq"])


def msg_list(session_id: str) -> list[dict]:
    rows = _get_conn().execute(
        "SELECT role, content, persona_id, seq, created_at FROM chat_messages "
        "WHERE session_id=? ORDER BY seq ASC",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def msg_list_after_seq(session_id: str, after_seq: int) -> list[dict]:
    rows = _get_conn().execute(
        "SELECT role, content, persona_id, seq FROM chat_messages "
        "WHERE session_id=? AND seq > ? ORDER BY seq ASC",
        (session_id, after_seq),
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Feedback
# --------------------------------------------------------------------------- #


def feedback_add(user_id: str | None, content: str) -> None:
    _get_conn().execute(
        "INSERT INTO feedback (user_id, content, created_at) VALUES (?, ?, ?)",
        (user_id, content, now()),
    )


# --------------------------------------------------------------------------- #
# Housekeeping
# --------------------------------------------------------------------------- #


def warmup() -> None:
    """初始化连接 + schema。api.py 启动时调一次。"""
    _get_conn()


def db_path() -> str:
    return str(_DB_PATH)
