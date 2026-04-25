"""LIFEE API — FastAPI wrapper for the CLI debate engine

Exposes the same interface as the Cloudflare Worker so the existing
frontend can connect directly.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path as _Path

# Resolve .env at the project root (two levels up from this file) so the backend
# loads secrets regardless of which cwd uvicorn was started from.
load_dotenv(_Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="LIFEE API")

# 知识库：懒加载，启动时只记录路径
_knowledge_managers: dict = {}  # role_name → MemoryManager (lazy)
_knowledge_paths: dict = {}     # role_name → (db_path, knowledge_lang)
_knowledge_embedding = None     # shared embedding provider
_km_initialized = False

# 会话缓存：session_id → (Session, Moderator, participants, last_access_time)
_sessions: dict = {}
_SESSION_TTL = 3600  # 1小时过期


# ═══════════════════════════════════════════════════════════════════════
#  Detached generation (truly async streams — survive client disconnect)
# ═══════════════════════════════════════════════════════════════════════
# When a user hits /debate-stream, the generator work is spawned as an
# asyncio.Task tied to `_active_generations[session_id]` (NOT the HTTP
# request). Any SSE connection — first or later — subscribes to the same
# in-memory event log. Close the tab: the task keeps running, DB keeps
# getting PATCHed. Reopen: subscribe, see everything already generated +
# the rest as it arrives.
import asyncio as _asyncio

class _GenState:
    __slots__ = ("events", "subscribers", "done", "task", "finished_at")

    def __init__(self):
        self.events: list[str] = []              # full SSE event log (for replay)
        self.subscribers: list[_asyncio.Queue] = []
        self.done = _asyncio.Event()
        self.task: "_asyncio.Task | None" = None
        self.finished_at: "float | None" = None

    def publish(self, event: str) -> None:
        self.events.append(event)
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def subscribe(self) -> "_asyncio.Queue[str | None]":
        q: _asyncio.Queue = _asyncio.Queue()
        for e in self.events:                    # replay history
            q.put_nowait(e)
        if self.done.is_set():
            q.put_nowait(None)                   # end-of-stream sentinel
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: "_asyncio.Queue") -> None:
        try:
            self.subscribers.remove(q)
        except ValueError:
            pass

    def finish(self) -> None:
        import time as _t
        self.done.set()
        self.finished_at = _t.time()
        for q in list(self.subscribers):
            try:
                q.put_nowait(None)
            except Exception:
                pass


_active_generations: dict[str, _GenState] = {}


def _is_active_generation(sid: str) -> bool:
    state = _active_generations.get(sid)
    return bool(state and not state.done.is_set())


async def _run_generation_task(sid: str, state: _GenState, stream_iter):
    """Background task: drain the SSE generator into the broadcast queue."""
    try:
        async for event in stream_iter:
            state.publish(event)
    except Exception as e:
        import traceback; traceback.print_exc()
        state.publish(f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n")
    finally:
        state.finish()
        # GC: drop state 60s after done (frees memory; late clients already
        # have fallback via Supabase DB refetch)
        try:
            await _asyncio.sleep(60)
            cur = _active_generations.get(sid)
            if cur is state and cur.done.is_set() and not cur.subscribers:
                _active_generations.pop(sid, None)
        except _asyncio.CancelledError:
            pass


async def _observer_stream(sid: str):
    """Per-client SSE generator that reads from the detached task's broadcast."""
    state = _active_generations.get(sid)
    if not state:
        return
    q = state.subscribe()
    try:
        while True:
            event = await q.get()
            if event is None:
                break
            yield event
    finally:
        state.unsubscribe(q)

# ---- Credits 系统（本地 SQLite 持久化，见 lifee/store.py） ----
GUEST_CREDITS = 6
REGISTER_BONUS = 7   # 注册奖励（叠加在 Guest 剩余余额上）
REDEEM_CREDITS = 100

# store 模块下方通过 _store 引用（见 /auth/* 端点块）


def _initial_balance(uid: str) -> int:
    return REGISTER_BONUS if uid.startswith("user:") else GUEST_CREDITS


async def _get_balance(uid: str) -> int:
    """获取余额，新用户按初始额度建档。SQLite 本地读写几乎不可能失败。"""
    from lifee import store as _s
    try:
        return await asyncio.to_thread(_s.credits_ensure, uid, _initial_balance(uid))
    except Exception as e:
        print(f"[_get_balance] {uid}: {type(e).__name__}: {e}")
        return _initial_balance(uid)


async def _migrate_balance(from_uid: str, to_uid: str):
    """把 from_uid 的余额合并到 to_uid（IP → cookie / guest → user 迁移）。失败静默。"""
    if not from_uid or from_uid == to_uid:
        return
    from lifee import store as _s
    try:
        await asyncio.to_thread(_s.credits_migrate, from_uid, to_uid)
    except Exception:
        return


async def _deduct(uid: str, amount: int = 1) -> bool:
    from lifee import store as _s
    return await asyncio.to_thread(_s.credits_debit, uid, amount, "chat")


async def _redeem(uid: str, code: str) -> tuple[bool, str]:
    from lifee import store as _s
    ok, msg, _ = await asyncio.to_thread(_s.redeem_use, code, uid)
    return ok, msg


async def _generate_redeem_codes(n: int = 10, credits_each: int = 100) -> list[str]:
    import secrets
    codes = [secrets.token_hex(4).upper() for _ in range(n)]
    from lifee import store as _s
    await asyncio.to_thread(_s.redeem_codes_bulk_insert, [(c, credits_each) for c in codes])
    return codes


_RELEASE_URL = "https://github.com/Ruzhenzrose/LIFEE/releases/download/knowledge-v1"

# GitHub Release 上可用的 db 文件
_RELEASE_DBS = [
    "drucker", "welch", "buffett", "munger", "audreyhepburn",
    "krishnamurti", "turing", "shannon", "vonneumann", "lacan",
]


def _download_db(role_name: str, dest: Path) -> bool:
    """从 GitHub Release 下载 knowledge.db"""
    import urllib.request
    url = f"{_RELEASE_URL}/{role_name}.knowledge.db"
    try:
        print(f"[knowledge] Downloading {role_name}...", end=" ", flush=True)
        urllib.request.urlretrieve(url, str(dest))
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"{size_mb:.0f}MB")
        return True
    except Exception as e:
        print(f"failed ({e})")
        return False


async def _init_knowledge():
    """启动时下载知识库文件，但不打开连接（连接懒加载）"""
    global _km_initialized, _knowledge_embedding
    if _km_initialized:
        return
    _km_initialized = True

    from lifee.roles import RoleManager
    from lifee.memory import create_embedding_provider

    rm = RoleManager()

    priority_roles = os.getenv("RAG_ROLES", ",".join(_RELEASE_DBS)).split(",")
    target_roles = [r.strip() for r in priority_roles if r.strip()]

    google_key = os.getenv("GOOGLE_API_KEY", "")
    if not google_key:
        print("[knowledge] No GOOGLE_API_KEY, skipping RAG")
        return

    try:
        _knowledge_embedding = create_embedding_provider(google_api_key=google_key)
    except Exception as e:
        print(f"[knowledge] Failed to create embedding provider: {e}")
        return

    bg_tasks: list = []  # (role_name, db_path, knowledge_dir, knowledge_lang)

    for role_name in target_roles:
        try:
            db_path = rm.get_knowledge_db_path(role_name)
            local_dir = rm.get_knowledge_dir(role_name)
            has_local = False
            if local_dir:
                src_files = list(local_dir.rglob("*.md")) + list(local_dir.rglob("*.txt"))
                has_local = any(f.is_file() for f in src_files)

            if has_local:
                # 本地有语料 → 用本地索引（跳过 Release 下载）
                role_info = rm.get_role_info(role_name)
                knowledge_lang = role_info.get("knowledge_lang", "English")
                if db_path.exists():
                    # db 已存在（上次索引过或 Release 下载过）→ 直接用，不进后台队列。
                    # 如果要重新索引（比如语料变了），手动删 db 再启动。
                    _knowledge_paths[role_name] = (db_path, knowledge_lang)
                    print(f"[knowledge] {role_name}: local db ready")
                else:
                    # 只有 db 缺失时才后台重建（首次启动 / 主动清除后）
                    print(f"[knowledge] {role_name}: no db, will build in background")
                    bg_tasks.append((role_name, db_path, local_dir, knowledge_lang))
                continue

            # 无本地语料 → 从 Release 下载 pre-built db
            if not db_path.exists() and role_name in _RELEASE_DBS:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                if not _download_db(role_name, db_path):
                    continue

            if db_path.exists():
                role_info = rm.get_role_info(role_name)
                knowledge_lang = role_info.get("knowledge_lang", "English")
                _knowledge_paths[role_name] = (db_path, knowledge_lang)
                print(f"[knowledge] {role_name}: downloaded (connection lazy)")
        except Exception as e:
            print(f"[knowledge] {role_name}: failed ({e})")

    print(f"[knowledge] {len(_knowledge_paths)} roles ready (connections lazy)")

    if bg_tasks:
        print(f"[knowledge] {len(bg_tasks)} roles queued for background indexing")
        asyncio.create_task(_background_index(rm, bg_tasks))


async def _background_index(rm, tasks: list):
    """后台逐个 role 跑增量索引，不阻塞 web 启动。"""
    from lifee.memory import MemoryManager
    for role_name, db_path, knowledge_dir, knowledge_lang in tasks:
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            manager = MemoryManager(db_path, _knowledge_embedding, knowledge_lang=knowledge_lang)
            files = list(knowledge_dir.rglob("*.md")) + list(knowledge_dir.rglob("*.txt"))
            files = [f for f in files if f.is_file()]
            need_index = [f for f in files if manager._needs_reindex(f)]
            if not need_index:
                _knowledge_paths[role_name] = (db_path, knowledge_lang)
                print(f"[knowledge:bg] {role_name}: up-to-date ({len(files)} files)")
                continue

            total = len(need_index)
            print(f"[knowledge:bg] {role_name}: indexing {total} files...", flush=True)
            done = 0
            failed = 0
            for f in need_index:
                try:
                    await manager.index_file(f)
                except Exception as e:
                    failed += 1
                    print(f"[knowledge:bg] {role_name}: {f.name} failed ({e})", flush=True)
                done += 1
                if done % 5 == 0 or done == total:
                    print(f"[knowledge:bg] {role_name}: {done}/{total}", flush=True)

            _knowledge_paths[role_name] = (db_path, knowledge_lang)
            _knowledge_managers.pop(role_name, None)
            print(f"[knowledge:bg] {role_name}: done ({total - failed}/{total})", flush=True)
        except Exception as e:
            print(f"[knowledge:bg] {role_name}: fatal ({e})", flush=True)


def _get_knowledge_manager(role_name: str):
    """懒加载：第一次访问时才打开 SQLite 连接"""
    if role_name in _knowledge_managers:
        return _knowledge_managers[role_name]
    if role_name not in _knowledge_paths or not _knowledge_embedding:
        return None

    db_path, knowledge_lang = _knowledge_paths[role_name]
    if not db_path.exists():
        return None

    from lifee.memory import MemoryManager
    try:
        km = MemoryManager(db_path, _knowledge_embedding, knowledge_lang=knowledge_lang)
        stats = km.get_stats()
        count = stats.get("chunk_count", 0)
        if count > 0:
            _knowledge_managers[role_name] = km
            print(f"[knowledge] {role_name}: loaded {count} chunks (on demand)")
            return km
    except Exception as e:
        print(f"[knowledge] {role_name}: lazy load failed ({e})")
    return None


@app.on_event("startup")
async def startup():
    await _init_knowledge()
    # 本地 SQLite 热身，建表 / 打开 WAL
    try:
        from lifee import store as _s
        await asyncio.to_thread(_s.warmup)
        print(f"[store] ready ({_s.db_path()})")
    except Exception as e:
        print(f"[store] warmup failed: {type(e).__name__}: {e}")


@app.on_event("shutdown")
async def shutdown():
    pass

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_COOKIE_NAME = "lifee_uid"
_COOKIE_MAX_AGE = 365 * 24 * 3600  # 1 年


def _get_ip_uid(request: Request) -> str:
    """从 IP 生成 uid"""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host
    return f"ip:{ip}"


async def _resolve_uid(request: Request) -> str:
    """解析真实 uid：cookie 有效（有对应 user_credits 行）→ 用 cookie，否则打回 IP 池。"""
    cookie_uid = request.cookies.get(_COOKIE_NAME, "")
    if cookie_uid:
        from lifee import store as _s
        try:
            bal = await asyncio.to_thread(_s.credits_get, cookie_uid)
            if bal is not None:
                return cookie_uid
        except Exception:
            return cookie_uid
    return _get_ip_uid(request)


def _set_uid_cookie(response: Response, uid: str):
    """种 httponly cookie"""
    response.set_cookie(
        _COOKIE_NAME, uid,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


class PersonaInput(BaseModel):
    id: str
    name: str
    knowledge: str = ""
    soul: str = ""      # AI-generated persona system prompt (non-empty for gen-* personas)
    emoji: str = "✨"   # display emoji for generated personas


class DecisionRequest(BaseModel):
    situation: str = ""
    userInput: str = ""
    personas: list[PersonaInput] = []
    context: str = ""
    moderator: bool = False  # 追问模式，默认关闭，用户开启
    sessionId: str = ""  # 会话 ID，空则新建
    userId: str = ""     # Supabase user ID（登录用户）
    language: str = ""   # 偏好语言（Chinese/English/空=自动）
    webSearch: bool = False  # 网络搜索开关
    maxSpeakers: int = 0    # 每轮最多发言人数（0=全部）


class FollowupTranscriptItem(BaseModel):
    role: str = "user"   # "user" | "assistant"
    content: str = ""
    name: str = ""       # "LIFEE" for prior follow-up cards; display name for personas


class FollowupRequest(BaseModel):
    userInput: str = ""
    personas: list[PersonaInput] = []
    history: list[FollowupTranscriptItem] = []  # Prior Q&A exchanges (including the current userInput at the end is fine)


def _get_provider():
    """创建 LLM Provider（不依赖 CLI 模块，避免 msvcrt 导入问题）"""
    from lifee.config.settings import settings
    provider_name = (os.getenv("API_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or settings.llm_provider).lower()

    if provider_name == "gemini":
        from lifee.providers import GeminiProvider
        return GeminiProvider(
            api_key=os.getenv("GOOGLE_API_KEY") or settings.google_api_key,
            model=os.getenv("LLM_MODEL") or settings.gemini_model or "gemini-2.0-flash",
        )
    elif provider_name == "claude":
        from lifee.providers import ClaudeProvider
        return ClaudeProvider(
            api_key=os.getenv("ANTHROPIC_API_KEY") or settings.anthropic_api_key,
            model=os.getenv("LLM_MODEL") or settings.claude_model or "claude-sonnet-4-20250514",
        )
    elif provider_name == "deepseek":
        from lifee.providers.openai_compat import DeepSeekProvider
        return DeepSeekProvider(
            api_key=os.getenv("DEEPSEEK_API_KEY") or settings.deepseek_api_key,
            model=os.getenv("LLM_MODEL") or settings.deepseek_model or "deepseek-chat",
        )
    else:
        raise ValueError(f"Unsupported provider for API: {provider_name}")


def _match_role(persona_id: str, persona_name: str) -> Optional[str]:
    """将前端的 persona id/name 映射到 CLI 的 role name"""
    from lifee.roles import RoleManager
    rm = RoleManager()
    available = rm.list_roles()

    # 直接匹配 role 目录名（兼容连字符/空格差异）
    pid = persona_id.lower().replace("-", "").replace(" ", "")
    pname = persona_name.lower().replace("-", "").replace(" ", "")
    for role in available:
        role_clean = role.lower().replace("-", "").replace(" ", "")
        if pid == role_clean or pname == role_clean or persona_id.lower() == role.lower():
            return role

    # 模糊匹配（display name）
    for role in available:
        info = rm.get_role_info(role)
        display = info.get("display_name", "").lower()
        if persona_name.lower() in display or display in persona_name.lower():
            return role

    return None



@app.get("/")
async def root(request: Request):
    index = Path(__file__).parent.parent / "web" / "ui" / "index.html"
    if index.exists():
        resp = FileResponse(index)
        if not request.cookies.get(_COOKIE_NAME):
            # 新用户：种 cookie，把 IP 余额迁移到 cookie uid
            new_uid = str(uuid4())
            ip_uid = _get_ip_uid(request)  # "ip:x.x.x.x"
            await _migrate_balance(ip_uid, new_uid)
            _set_uid_cookie(resp, new_uid)
        return resp
    return {"status": "ok", "service": "LIFEE API"}


@app.get("/debug-env")
async def debug_env():
    """显示环境变量（调试用）"""
    import sys
    key = os.getenv("GOOGLE_API_KEY", "NOT SET")
    provider = os.getenv("LLM_PROVIDER", "NOT SET")
    from lifee import store as _s
    return {
        "GOOGLE_API_KEY": key[:10] + "..." if key != "NOT SET" else key,
        "LLM_PROVIDER": provider,
        "API_LLM_PROVIDER": os.getenv("API_LLM_PROVIDER", "NOT SET"),
        "DB_PATH": _s.db_path(),
        "RESEND_CONFIGURED": bool(os.getenv("RESEND_API_KEY", "")),
        "JWT_CONFIGURED": bool(os.getenv("JWT_SECRET", "")),
        "python_version": sys.version,
    }


# ---- Turnstile 人机验证 ----
_TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "1x0000000000000000000000000000000AA")  # 测试 key


class TurnstileRequest(BaseModel):
    token: str


@app.get("/turnstile-key")
async def turnstile_key():
    """前端获取 Turnstile sitekey"""
    return {"sitekey": os.getenv("TURNSTILE_SITEKEY", "1x00000000000000000000AA")}


@app.post("/verify-human")
async def verify_human(req: TurnstileRequest, request: Request, response: Response):
    """验证 Turnstile token，通过后种 verified cookie"""
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data={
            "secret": _TURNSTILE_SECRET,
            "response": req.token,
            "remoteip": request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host,
        })
        result = r.json()

    if result.get("success"):
        response.set_cookie("lifee_verified", "1", max_age=365 * 24 * 3600, httponly=True, samesite="lax")
        return {"ok": True}
    return {"ok": False, "error": result.get("error-codes", [])}


# ---- Auth API（自家 email+password+OTP，替换 Supabase Auth）----
from lifee import store as _store
from lifee import auth as _auth


def _current_user(request: Request) -> dict | None:
    """从 JWT cookie 解析当前用户。返回 {id, email} 或 None。"""
    token = request.cookies.get(_auth.cookie_name(), "")
    if not token:
        return None
    payload = _auth.decode_token(token)
    if not payload:
        return None
    return {"id": payload.get("sub"), "email": payload.get("email")}


def _set_auth_cookie(response: Response, user_id: str, email: str):
    response.set_cookie(
        _auth.cookie_name(),
        _auth.make_token(user_id, email),
        max_age=_auth.cookie_max_age(),
        httponly=True,
        samesite="lax",
    )


class SignupRequest(BaseModel):
    email: str
    password: str


class VerifyOtpRequest(BaseModel):
    email: str
    code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ResendOtpRequest(BaseModel):
    email: str


def _normalize_email(e: str) -> str:
    return (e or "").strip().lower()


@app.post("/auth/signup")
async def auth_signup(req: SignupRequest):
    """注册：先建号（未验证）→ 生成 OTP → 发邮件。客户端随后调 /auth/verify-otp 完成。"""
    email = _normalize_email(req.email)
    if not email or "@" not in email:
        return {"ok": False, "message": "Invalid email"}
    if len(req.password) < 6:
        return {"ok": False, "message": "Password must be at least 6 characters"}

    try:
        existing = await asyncio.to_thread(_store.user_by_email, email)
        if existing:
            if existing.get("email_verified"):
                return {"ok": False, "message": "Email already registered"}
            # 未验证的旧号：更新密码，重新发 OTP（允许"没收到第一封"的用户重试）
            await asyncio.to_thread(_store.user_set_password, existing["id"], _auth.hash_password(req.password))
            user_id = existing["id"]
        else:
            user_id = await asyncio.to_thread(_store.user_create, email, _auth.hash_password(req.password))
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:
        print(f"[/auth/signup] {type(e).__name__}: {e}")
        return {"ok": False, "message": "Signup failed, please retry"}

    code = await asyncio.to_thread(_store.otp_create, email, "signup", 600)
    await _auth.send_otp_email(email, code, "signup")
    return {"ok": True, "message": "Verification code sent", "user_id": user_id}


@app.post("/auth/verify-otp")
async def auth_verify_otp(req: VerifyOtpRequest, response: Response):
    """校验 OTP 完成注册 → 发 JWT cookie。"""
    email = _normalize_email(req.email)
    code = (req.code or "").strip()
    ok = await asyncio.to_thread(_store.otp_consume, email, code, "signup")
    if not ok:
        return {"ok": False, "message": "Invalid or expired code"}
    user = await asyncio.to_thread(_store.user_by_email, email)
    if not user:
        return {"ok": False, "message": "User not found"}
    await asyncio.to_thread(_store.user_set_verified, user["id"])
    _set_auth_cookie(response, user["id"], email)
    return {"ok": True, "user": {"id": user["id"], "email": email}}


@app.post("/auth/resend-otp")
async def auth_resend_otp(req: ResendOtpRequest):
    email = _normalize_email(req.email)
    if not email:
        return {"ok": False, "message": "Invalid email"}
    user = await asyncio.to_thread(_store.user_by_email, email)
    if not user or user.get("email_verified"):
        # 不暴露用户是否存在
        return {"ok": True, "message": "Verification code sent (if needed)"}
    code = await asyncio.to_thread(_store.otp_create, email, "signup", 600)
    await _auth.send_otp_email(email, code, "signup")
    return {"ok": True, "message": "Verification code sent"}


@app.post("/auth/login")
async def auth_login(req: LoginRequest, response: Response):
    email = _normalize_email(req.email)
    user = await asyncio.to_thread(_store.user_by_email, email)
    if not user:
        return {"ok": False, "message": "Invalid email or password"}
    if not await asyncio.to_thread(_auth.verify_password, req.password, user["password_hash"]):
        return {"ok": False, "message": "Invalid email or password"}
    if not user.get("email_verified"):
        # 未验证：重新发 OTP，让客户端走验证流程
        code = await asyncio.to_thread(_store.otp_create, email, "signup", 600)
        await _auth.send_otp_email(email, code, "signup")
        return {"ok": False, "message": "Email not verified", "needs_verify": True}
    _set_auth_cookie(response, user["id"], email)
    return {"ok": True, "user": {"id": user["id"], "email": email}}


@app.post("/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(_auth.cookie_name())
    return {"ok": True}


def _user_payload(u: dict) -> dict:
    """返回前端期望的 supabase-style user 形状（带 user_metadata.name）。"""
    name = ""
    try:
        name = _store.user_get_name(u["id"])
    except Exception:
        pass
    return {
        "id": u["id"],
        "email": u["email"],
        "user_metadata": {"name": name} if name else {},
    }


@app.get("/auth/me")
async def auth_me(request: Request):
    u = _current_user(request)
    if not u:
        return {"user": None}
    return {"user": await asyncio.to_thread(_user_payload, u)}


# ---- User profile（替换原 supabase.profiles）----


@app.get("/user/profile")
async def user_profile_get(request: Request):
    u = _current_user(request)
    if not u:
        return {"user": None}
    def _load():
        return _store.user_get_memory(u["id"]), _store.user_get_name(u["id"])
    mem, name = await asyncio.to_thread(_load)
    return {
        "user": {"id": u["id"], "email": u["email"], "user_metadata": {"name": name} if name else {}},
        "user_memory": mem,
        "display_name": name,
    }


class UserMemoryRequest(BaseModel):
    user_memory: str


@app.patch("/user/memory")
async def user_memory_set(req: UserMemoryRequest, request: Request):
    u = _current_user(request)
    if not u:
        return {"ok": False, "message": "not logged in"}
    await asyncio.to_thread(_store.user_set_memory, u["id"], req.user_memory)
    return {"ok": True}


class UserNameRequest(BaseModel):
    name: str = ""


@app.patch("/user/name")
async def user_name_set(req: UserNameRequest, request: Request):
    u = _current_user(request)
    if not u:
        return {"ok": False, "message": "not logged in"}
    await asyncio.to_thread(_store.user_set_name, u["id"], req.name or "")
    return {"ok": True, "user": await asyncio.to_thread(_user_payload, u)}


@app.get("/test-llm")
async def test_llm():
    """测试 LLM provider 是否正常工作"""
    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        response = await provider.chat(
            messages=[Message(role=MessageRole.USER, content="Say hello in one word.")],
            max_tokens=50,
            temperature=0.5,
        )
        return {"provider": provider.name, "model": provider.model, "response": response.content}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


# ---- Credits API ----

@app.get("/credits")
async def get_credits(request: Request, response: Response, userId: str = ""):
    """查询余额（登录用户 → cookie → IP）"""
    if userId:
        uid = f"user:{userId}"
    else:
        uid = await _resolve_uid(request)
        if not request.cookies.get(_COOKIE_NAME):
            new_uid = str(uuid4())
            await _migrate_balance(uid, new_uid)
            _set_uid_cookie(response, new_uid)
            uid = new_uid
    return {"balance": await _get_balance(uid)}


class RedeemRequest(BaseModel):
    code: str
    userId: str = ""


@app.post("/credits/redeem")
async def redeem(req: RedeemRequest, request: Request):
    """兑换码充值"""
    if req.userId:
        uid = f"user:{req.userId}"
    else:
        uid = await _resolve_uid(request)
        if not uid:
            return {"ok": False, "message": "no session", "balance": 0}
    ok, msg = await _redeem(uid, req.code.strip().upper())
    return {"ok": ok, "message": msg, "balance": await _get_balance(uid)}


@app.get("/credits/generate/{n}")
async def gen_codes(n: int = 10, credits: int = 100):
    """生成兑换码（管理员用）。credits 参数指定面额，默认 100"""
    codes = await _generate_redeem_codes(n, credits)
    return {"codes": codes, "credits_each": credits}


# ---- 会话存档 API ----

async def _save_message(session_id: str, user_id: str, role: str, content: str, persona_id: str = "", seq: int = 0):
    """存一条消息到 SQLite。空内容跳过。"""
    if not content.strip():
        return
    try:
        from lifee import store as _s
        await asyncio.to_thread(
            _s.msg_save, session_id, role, content,
            seq=(seq if seq else None), persona_id=(persona_id or None),
        )
    except Exception as e:
        print(f"[_save_message] {type(e).__name__}: {e}")


async def _insert_message_stub(session_id: str, user_id: str, role: str, persona_id: str, seq: int):
    """Insert an empty assistant message row at the start of a persona's turn。
    后续 chunks 用相同 (session_id, seq) 覆盖 content。"""
    try:
        from lifee import store as _s
        await asyncio.to_thread(
            _s.msg_save, session_id, role, "",
            seq=seq, persona_id=(persona_id or None),
        )
    except Exception as e:
        print(f"[_insert_message_stub] {type(e).__name__}: {e}")


async def _patch_message_content(session_id: str, seq: int, content: str):
    """Update the content of an in-flight message row keyed by (session_id, seq)。
    只改 content，不碰 persona_id。"""
    try:
        from lifee import store as _s
        await asyncio.to_thread(_s.msg_update_content, session_id, seq, content)
    except Exception:
        pass


async def _log_conversation(uid: str, role: str, persona_id: str, content_preview: str):
    """对话日志（Guest 也记）。amount=0 不影响余额。"""
    preview = content_preview[:100].replace('\n', ' ')
    try:
        from lifee import store as _s
        await asyncio.to_thread(_s.credits_ensure, uid, _initial_balance(uid))
        await asyncio.to_thread(_s.credits_log, uid, 0, f"msg:{role}:{persona_id}:{preview}")
    except Exception:
        pass


async def _ensure_chat_session(session_id: str, user_id: str, title: str = "New Chat", personas: list = None):
    """确保 chat_session 存在；存在就 touch updated_at。"""
    try:
        from lifee import store as _s
        created = await asyncio.to_thread(
            _s.session_ensure, session_id, user_id, title=title, personas=personas or [],
        )
        if not created:
            await asyncio.to_thread(_s.session_update, session_id)
    except Exception:
        pass


@app.get("/sessions")
async def list_sessions(request: Request, userId: str = ""):
    """列出用户的会话（已去掉没消息的空 session）"""
    if not userId:
        return {"sessions": []}
    try:
        from lifee import store as _s
        rows = await asyncio.to_thread(_s.session_list, userId, 20)
    except Exception as e:
        print(f"[/sessions] {type(e).__name__}: {e}")
        return {"sessions": []}
    sessions = [r for r in rows if r.get("message_count", 0) > 0]
    for r in sessions:
        r.pop("message_count", None)
    return {"sessions": sessions}


# Alias → canonical persona id. chat_sessions.personas historically stored
# display names (Chinese or English) rather than ids, so we normalise here
# before aggregating.
_PERSONA_ALIASES: dict[str, str] = {
    # Chinese
    "克里希那穆提": "krishnamurti",
    "拉康": "lacan",
    "西蒙娜·德·波伏瓦": "Simone de Beauvoir",
    "巴菲特": "buffett",
    "芒格": "munger",
    "德鲁克": "drucker",
    "韦尔奇": "welch",
    "香农": "shannon",
    "图灵": "turing",
    "冯·诺依曼": "vonneumann",
    "奥黛丽·赫本": "audrey-hepburn",
    # English display names
    "Krishnamurti": "krishnamurti",
    "Lacan": "lacan",
    "Warren Buffett": "buffett",
    "Charlie Munger": "munger",
    "Peter Drucker": "drucker",
    "Jack Welch": "welch",
    "Claude Shannon": "shannon",
    "Alan Turing": "turing",
    "John von Neumann": "vonneumann",
    "Audrey Hepburn": "audrey-hepburn",
}


def _canonical_persona_id(raw: str) -> str:
    if not raw:
        return ""
    if raw in _PERSONA_ALIASES:
        return _PERSONA_ALIASES[raw]
    # fallback: lowercase, strip whitespace — matches many persona ids
    return raw.lower().replace(" ", "")


class FeedbackRequest(BaseModel):
    content: str
    userId: str = ""
    email: str = ""
    url: str = ""


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request):
    """Store user feedback in Supabase `feedback` table.

    Expected table schema (create in Supabase SQL editor):
        create table feedback (
            id uuid primary key default gen_random_uuid(),
            user_id uuid,
            email text,
            content text not null,
            url text,
            created_at timestamptz default now()
        );
    """
    content = (req.content or "").strip()
    if not content:
        return {"ok": False, "message": "empty feedback"}
    if len(content) > 5000:
        return {"ok": False, "message": "feedback too long (max 5000 chars)"}
    # 把 email/url 附带在 content 里留档（feedback 表只有 user_id+content）
    extras = []
    if req.email:
        extras.append(f"email={req.email.strip()[:200]}")
    if req.url:
        extras.append(f"url={req.url.strip()[:500]}")
    full = content + ("\n---\n" + " ".join(extras) if extras else "")
    try:
        from lifee import store as _s
        await asyncio.to_thread(_s.feedback_add, req.userId or None, full)
    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}
    return {"ok": True}


@app.get("/personas/hot")
async def hot_personas(days: int = 7, limit: int = 8):
    """Site-wide hot personas in the last N days.

    Aggregates from chat_sessions.personas over updated_at >= now - days.
    Each session counts once per persona (so heavy single-session users
    don't dominate the ranking the way /chat_messages would).
    """
    import time as _time
    cutoff_ts = int(_time.time()) - days * 86400
    counts: dict[str, int] = {}
    try:
        from lifee import store as _s
        import json as _json
        def _scan() -> dict[str, int]:
            conn = _s._get_conn()
            rows = conn.execute(
                "SELECT personas FROM chat_sessions WHERE updated_at >= ?",
                (cutoff_ts,),
            ).fetchall()
            c: dict[str, int] = {}
            for r in rows:
                try:
                    arr = _json.loads(r["personas"] or "[]")
                except Exception:
                    arr = []
                for raw in arr:
                    if not raw or raw in ("user", "system", "lifee-followup"):
                        continue
                    k = _canonical_persona_id(raw)
                    c[k] = c.get(k, 0) + 1
            return c
        counts = await asyncio.to_thread(_scan)
    except Exception as e:
        print(f"[/personas/hot] {type(e).__name__}: {e}")
        return {"hot": []}
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:max(1, limit)]
    return {"hot": [{"id": pid, "count": n} for pid, n in ranked]}


@app.get("/sessions/{session_id}/generation-status")
async def generation_status(session_id: str):
    """Cheap probe: is there a detached generation task running for this session?

    The frontend hits this before opening observe-stream so the common case
    (nothing to observe) doesn't log a 404 to the browser's Network tab.
    Always returns 200 with {active: bool}.
    """
    return {"active": _is_active_generation(session_id)}


@app.get("/sessions/{session_id}/observe-stream")
async def observe_stream(session_id: str):
    """Attach an SSE observer to an in-flight generation for this session.

    Returns 404 if no detached task is running (client falls back to DB state).
    Works across tabs/devices: each call creates a fresh subscriber queue that
    replays the task's full event log + tails future events until it finishes.
    """
    if not _is_active_generation(session_id):
        return JSONResponse({"error": "no active generation"}, status_code=404)
    return StreamingResponse(
        _observer_stream(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/sessions/{session_id}/cancel")
async def cancel_generation(session_id: str):
    """Cancel the detached generation task for this session if one is running.

    Stops producing further tokens. Whatever has already been streamed / persisted
    stays (stop-and-keep semantics). Returns 200 either way — idempotent.
    """
    state = _active_generations.get(session_id)
    if state is None:
        return {"ok": True, "cancelled": False}
    try:
        if state.task and not state.task.done():
            state.task.cancel()
        state.done.set()
    except Exception:
        pass
    return {"ok": True, "cancelled": True}


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取会话消息 + 最新 follow-up options。"""
    import traceback
    try:
        from lifee import store as _s
        def _load():
            msgs = _s.msg_list(session_id)
            sess = _s.session_get(session_id)
            opts = sess.get("last_options") if sess else {}
            if not isinstance(opts, list):
                # last_options 历史上是 list，但 session_get 会 json.loads 成 dict 时返回 {}，这里兼容
                opts = opts.get("options", []) if isinstance(opts, dict) else []
            return msgs, opts
        messages, options = await asyncio.to_thread(_load)
        return {"messages": messages, "options": options}
    except Exception as e:
        print(f"[sessions/{session_id}/messages] failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return {"messages": [], "options": [], "error": f"{type(e).__name__}: {e}"}


class SessionUpdateRequest(BaseModel):
    title: str = ""
    starred: bool = None


@app.patch("/sessions/{session_id}")
async def update_session(session_id: str, req: SessionUpdateRequest):
    """更新会话（重命名/Star）"""
    updates = {}
    if req.title:
        updates["title"] = req.title
    if req.starred is not None:
        updates["starred"] = req.starred
    if not updates:
        return {"ok": False, "message": "nothing to update"}
    try:
        from lifee import store as _s
        await asyncio.to_thread(lambda: _s.session_update(session_id, **updates))
        return {"ok": True}
    except Exception:
        return {"ok": False}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request, userId: str = ""):
    """软删除会话（标记 deleted=1，数据保留）。必须传 userId 防止误删他人的。"""
    if not userId:
        u = _current_user(request)
        if not u:
            return {"ok": False, "message": "not logged in"}
        userId = u["id"]
    try:
        from lifee import store as _s
        ok = await asyncio.to_thread(_s.session_soft_delete, session_id, userId)
        return {"ok": bool(ok)}
    except Exception:
        return {"ok": False}


# ---- 总结 API ----

class SummarizeRequest(BaseModel):
    sessionId: str = ""
    messages: list = []  # fallback: [{personaId, text}, ...]
    language: str = "Chinese"


@app.post("/summarize")
async def summarize_debate(req: SummarizeRequest):
    """总结每个角色的核心观点"""
    # 优先从 Supabase 加载消息（避免大 POST body）
    msgs = req.messages
    if req.sessionId and not msgs:
        try:
            from lifee import store as _s
            db_msgs = await asyncio.to_thread(_s.msg_list, req.sessionId)
            msgs = [{"personaId": m.get("persona_id") or "", "text": m.get("content", "")} for m in db_msgs]
        except Exception:
            pass

    if not msgs:
        return {"summaries": {}}

    # 按角色分组
    by_persona = {}
    for m in msgs:
        pid = m.get("personaId", "")
        if pid in ("user", "system", "lifee-followup", "moderator", ""):
            continue
        if pid not in by_persona:
            by_persona[pid] = []
        text = m.get("text", "")
        by_persona[pid].append(text)

    if not by_persona:
        return {"summaries": {}}

    # 构建 prompt
    parts = []
    for pid, texts in by_persona.items():
        combined = "\n".join(texts[-5:])  # 最近 5 条
        parts.append(f"【{pid}】:\n{combined}")

    prompt = f"""Summarize each participant's core viewpoint in 1-2 sentences. Reply in {req.language}.

Conversation:
{chr(10).join(parts)}

Reply in JSON format: {{"persona_id": "1-2 sentence summary", ...}}"""

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        messages = [Message(role=MessageRole.USER, content=prompt)]
        # 用流式收集，减少内存峰值 + 防超时
        chunks = []
        async for chunk in provider.stream(messages=messages, max_tokens=500, temperature=0.3):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        import json as _json
        if '```' in text:
            text = text.split('```')[1].replace('json', '', 1).strip()
        summaries = _json.loads(text)
        return {"summaries": summaries}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"summaries": {}, "error": str(e)}


# ---- Timeline API ----

class TimelineRequest(BaseModel):
    sessionId: str = ""
    messages: list = []
    language: str = "Chinese"
    situation: str = ""


@app.post("/timeline")
async def generate_timeline(req: TimelineRequest):
    """为A/B辩论生成两条人生时间线"""
    msgs = req.messages
    if req.sessionId and not msgs:
        try:
            from lifee import store as _s
            db_msgs = await asyncio.to_thread(_s.msg_list, req.sessionId)
            msgs = [{"personaId": m.get("persona_id") or "", "text": m.get("content", "")} for m in db_msgs]
        except Exception:
            pass

    if not msgs:
        return {"timelines": {}}

    by_persona: dict = {}
    for m in msgs:
        pid = m.get("personaId", "")
        if pid in ("user", "system", "lifee-followup", "moderator", ""):
            continue
        if pid not in by_persona:
            by_persona[pid] = []
        by_persona[pid].append(m.get("text", ""))

    situation = req.situation.strip()
    personas_list = list(by_persona.keys())
    if len(personas_list) < 1:
        return {"timelines": {}}

    parts = []
    for pid, texts in by_persona.items():
        combined = "\n".join(texts[-4:])
        parts.append(f"【{pid}的观点】:\n{combined}")

    prompt = f"""You are a life strategy advisor. Based on this debate about a key life decision, generate 2 concrete future timelines — one for each path/option being debated.

Situation: {situation or 'Major life decision'}

Debate content:
{chr(10).join(parts)}

Generate exactly 2 timelines in {req.language}. Each timeline should have 4-5 phases spanning 3 years.

Reply ONLY in this JSON format (no markdown, no extra text):
{{
  "option_a": {{
    "label": "Short path name (e.g. 加入公司)",
    "phases": [
      {{"period": "Now → Month 3", "title": "Phase title", "description": "Concrete description of what happens", "tags": ["tag1", "tag2"]}},
      {{"period": "Month 3 → 6", "title": "Phase title", "description": "...", "tags": ["tag1"]}},
      {{"period": "Month 6 → 12", "title": "Phase title", "description": "...", "tags": ["tag1", "tag2"]}},
      {{"period": "Year 1 → 2", "title": "Phase title", "description": "...", "tags": ["tag1"]}},
      {{"period": "Year 2 → 3", "title": "Phase title", "description": "...", "tags": ["tag1", "tag2"]}}
    ]
  }},
  "option_b": {{
    "label": "Short path name (e.g. 自主创业)",
    "phases": [
      {{"period": "Now → Month 3", "title": "Phase title", "description": "...", "tags": ["tag1"]}},
      {{"period": "Month 3 → 6", "title": "Phase title", "description": "...", "tags": ["tag1"]}},
      {{"period": "Month 6 → 12", "title": "Phase title", "description": "...", "tags": ["tag1", "tag2"]}},
      {{"period": "Year 1 → 2", "title": "Phase title", "description": "...", "tags": ["tag1"]}},
      {{"period": "Year 2 → 3", "title": "Phase title", "description": "...", "tags": ["tag1", "tag2"]}}
    ]
  }}
}}"""

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        messages_llm = [Message(role=MessageRole.USER, content=prompt)]
        chunks = []
        async for chunk in provider.stream(messages=messages_llm, max_tokens=1200, temperature=0.4):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        import json as _json
        if '```' in text:
            text = text.split('```')[1].replace('json', '', 1).strip()
        timelines = _json.loads(text)
        return {"timelines": timelines}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"timelines": {}, "error": str(e)}


# ---- 30-Day Plan API ----

class PlanRequest(BaseModel):
    sessionId: str = ""
    messages: list = []
    language: str = "Chinese"
    situation: str = ""
    chosenOption: str = ""


@app.post("/plan-30-days")
async def plan_30_days(req: PlanRequest):
    """生成前30天的周行动计划"""
    msgs = req.messages
    if req.sessionId and not msgs:
        try:
            from lifee import store as _s
            db_msgs = await asyncio.to_thread(_s.msg_list, req.sessionId)
            msgs = [{"personaId": m.get("persona_id") or "", "text": m.get("content", "")} for m in db_msgs]
        except Exception:
            pass

    debate_text = "\n".join(
        f"[{m.get('personaId','')}]: {m.get('text','')}"
        for m in (msgs or [])
        if m.get("personaId", "") not in ("system", "lifee-followup", "moderator")
    )[-3000:]

    situation = req.situation.strip()
    chosen = req.chosenOption.strip()

    prompt = f"""You are a life coach. Create a concrete 4-week action plan for the first 30 days.

Situation: {situation or 'Major life transition'}
{f'Chosen direction: {chosen}' if chosen else ''}

Debate context (for background):
{debate_text or '(no debate context)'}

Generate a 4-week plan in {req.language}. Each week should have a theme, a goal, and 3-4 concrete tasks with tags.

Reply ONLY in this JSON format (no markdown, no extra text):
{{
  "weeks": [
    {{
      "id": "week1",
      "label": "Week 1 — 听懂",
      "goal": "Week 1 goal — what you want to achieve by end of week",
      "tasks": [
        {{"title": "Task title", "description": "Specific action to take", "tags": ["tag1", "tag2"]}},
        {{"title": "Task title", "description": "Specific action to take", "tags": ["tag1"]}},
        {{"title": "Task title", "description": "Specific action to take", "tags": ["tag1", "tag2"]}}
      ]
    }},
    {{
      "id": "week2",
      "label": "Week 2 — 找空白",
      "goal": "Week 2 goal",
      "tasks": [...]
    }},
    {{
      "id": "week3",
      "label": "Week 3 — 出方案",
      "goal": "Week 3 goal",
      "tasks": [...]
    }},
    {{
      "id": "week4",
      "label": "Week 4 — 亮牌",
      "goal": "Week 4 goal",
      "tasks": [...]
    }}
  ]
}}"""

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        messages_llm = [Message(role=MessageRole.USER, content=prompt)]
        chunks = []
        async for chunk in provider.stream(messages=messages_llm, max_tokens=1500, temperature=0.4):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        import json as _json
        if '```' in text:
            text = text.split('```')[1].replace('json', '', 1).strip()
        plan = _json.loads(text)
        return {"plan": plan}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"plan": {}, "error": str(e)}


# ---- Persona Recommendation API ----

class RecommendPersonasRequest(BaseModel):
    situation: str = ""
    periods: list = []
    persona_ids: list = []


@app.post("/recommend-personas")
async def recommend_personas(req: RecommendPersonasRequest):
    """根据用户情境，用 LLM 推荐最相关的 4 个角色 ID"""
    if not req.situation.strip():
        return {"ids": []}

    ids_list = ", ".join(req.persona_ids) if req.persona_ids else "(none)"
    periods_str = ", ".join(req.periods) if req.periods else "none"

    prompt = (
        "You are a persona recommendation engine for a life-coaching debate app.\n\n"
        f"User's situation:\n{req.situation.strip()}\n\n"
        f"Life context tags: {periods_str}\n\n"
        f"Available persona IDs: {ids_list}\n\n"
        "Select exactly 2 persona IDs that would resonate most with this user's situation. "
        "Prioritise emotional fit first, then intellectual fit. "
        "Only use IDs from the available list. "
        'Reply ONLY with a JSON array of exactly 2 items, e.g. ["buffett","krishnamurti"]'
    )

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        messages = [Message(role=MessageRole.USER, content=prompt)]
        chunks = []
        async for chunk in provider.stream(messages=messages, max_tokens=40, temperature=0.3):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip()
        ids = json.loads(text)
        if not isinstance(ids, list):
            raise ValueError("not a list")
        # keep only valid ids and cap at 2
        valid = [i for i in ids if i in req.persona_ids][:2]
        return {"ids": valid}
    except Exception as e:
        print(f"[recommend-personas] failed: {e}")
        return {"ids": [], "error": str(e)}


# ---- Generate New Personas API ----

class GeneratePersonasRequest(BaseModel):
    situation: str = ""
    periods: list = []
    existing_ids: list = []   # IDs already in the recommend list (avoid duplicates)


async def _gemini_grounding_search(query: str) -> str:
    """Use Gemini with Google Search grounding to get web context.

    Uses GOOGLE_SEARCH_API_KEY if set, otherwise falls back to GOOGLE_API_KEY.
    Returns empty string if no key is available.
    """
    api_key = (
        os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )
    if not api_key:
        return ""
    try:
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
        }
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(url, json=payload)
            data = r.json()

        # Extract text from the response
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts_out = candidates[0].get("content", {}).get("parts", [])
        text_parts = [p.get("text", "") for p in parts_out if p.get("text")]
        result = " ".join(text_parts).strip()

        # Also extract grounding citations if present
        grounding = candidates[0].get("groundingMetadata", {})
        chunks = grounding.get("groundingChunks", [])
        sources = []
        for ch in chunks[:4]:
            web = ch.get("web", {})
            title = web.get("title", "")
            uri = web.get("uri", "")
            if title:
                sources.append(f"- {title}: {uri}")

        if sources:
            result += "\n\nSources:\n" + "\n".join(sources)

        return result[:1200]  # cap context size
    except Exception as e:
        print(f"[gemini-grounding] search failed: {e}")
        return ""


@app.post("/generate-personas")
async def generate_new_personas(req: GeneratePersonasRequest):
    """Use LLM (+ optional Tavily web search) to generate 1-2 brand-new persona definitions.

    These are distinct from the existing persona roster — the LLM picks real-world figures
    or archetypes that would be uniquely valuable for the user's situation and generates
    a full system prompt (soul) so they can participate in debates without needing disk files.
    """
    if not req.situation.strip():
        return {"personas": []}

    # Optional web search context via Gemini Grounding (uses GOOGLE_SEARCH_API_KEY or GOOGLE_API_KEY)
    search_ctx = ""
    google_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    if google_key:
        search_query = f"Who are the most insightful historical figures, thinkers or archetypes for someone dealing with: {req.situation[:120]}"
        search_ctx = await _gemini_grounding_search(search_query)

    periods_str = ", ".join(req.periods) if req.periods else "none"
    existing_str = ", ".join(req.existing_ids) if req.existing_ids else "(none)"
    search_section = f"\n\nWeb search context:\n{search_ctx}" if search_ctx else ""

    prompt = (
        "You are a persona-generation engine for a life-coaching app called LIFEE. "
        "Users share their life situations and get advice from real historical figures and famous people.\n\n"
        f"User situation: {req.situation.strip()}\n"
        f"Life context tags: {periods_str}\n"
        f"Already-recommended persona IDs (do NOT duplicate): {existing_str}"
        f"{search_section}\n\n"
        "Generate exactly 2 persona definitions based on REAL, FAMOUS historical figures or well-known public figures "
        "(NOT fictional or archetypal characters). "
        "Choose real people — philosophers, scientists, entrepreneurs, artists, writers, leaders, athletes — "
        "whose actual life experience and known worldview would genuinely illuminate this situation. "
        "Pick people who are somewhat surprising and non-obvious for this context, not the first cliché that comes to mind. "
        "Do NOT invent fictional archetypes. Every persona must be a real person with a verifiable life story.\n\n"
        "For each persona output:\n"
        "- id: slug like 'gen-firstname-lastname' (lowercase, hyphens, must start with 'gen-')\n"
        "- name: their real full name or most recognised name (max 25 chars)\n"
        "- role: a SHORT label in CAPS describing their identity/legacy (max 30 chars), "
        "e.g. 'STOIC EMPEROR', 'RENAISSANCE GENIUS', 'JAZZ INNOVATOR'\n"
        "- avatar: single emoji that fits their essence\n"
        "- voice: one sentence written in their authentic voice, capturing how they actually spoke/wrote (max 120 chars)\n"
        "- soul: a 200-300 word system prompt. Start with 'You are [Name].' "
        "Describe their real biography highlights, core beliefs, signature thinking style, "
        "how they would approach the user's situation, and their speech mannerisms. "
        "Write in second person. Make them feel like the real person, not a caricature. "
        "They should respond in the same language as the user.\n\n"
        'Reply ONLY with a JSON array of 2 objects with keys: id, name, role, avatar, voice, soul.\n'
        'Example: [{"id":"gen-simone-de-beauvoir","name":"Simone de Beauvoir","role":"EXISTENTIALIST WRITER",'
        '"avatar":"✒️","voice":"One is not born a woman, but becomes one.","soul":"You are Simone de Beauvoir..."}]'
    )

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        chunks = []
        async for chunk in provider.stream(
            messages=[Message(role=MessageRole.USER, content=prompt)],
            max_tokens=1200,
            temperature=0.8,
        ):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip()
        # strip trailing ``` if present
        if text.endswith("```"):
            text = text[:-3].strip()
        personas = json.loads(text)
        if not isinstance(personas, list):
            raise ValueError("not a list")
        # Validate structure and enforce gen- prefix
        valid = []
        for p in personas[:2]:
            pid = str(p.get("id", "")).strip()
            if not pid.startswith("gen-"):
                pid = f"gen-{pid}"
            soul = str(p.get("soul", "")).strip()
            if not soul or len(soul) < 50:
                continue
            valid.append({
                "id": pid,
                "name": str(p.get("name", pid))[:40],
                "role": str(p.get("role", ""))[:40].upper(),
                "avatar": str(p.get("avatar", "✨"))[:4],
                "voice": str(p.get("voice", ""))[:160],
                "soul": soul,
            })
        return {"personas": valid}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"personas": [], "error": str(e)}


# ---- User Memory API ----

class ExtractMemoryRequest(BaseModel):
    sessionId: str = ""
    userId: str = ""
    currentMemory: str = ""


@app.post("/extract-memory")
async def extract_memory(req: ExtractMemoryRequest):
    """从对话中自动提取用户信息，更新 user_memory"""
    if not req.userId:
        return {"updated": False, "error": "Not logged in"}

    # 查上次提取到的 seq
    last_seq = 0
    msgs = []
    if req.sessionId:
        try:
            from lifee import store as _s
            sess = await asyncio.to_thread(_s.session_get, req.sessionId)
            if sess:
                last_seq = int(sess.get("last_extract_msg_count") or 0)
            msgs = await asyncio.to_thread(_s.msg_list_after_seq, req.sessionId, last_seq)
        except Exception:
            pass

    if not msgs:
        return {"updated": False}

    # 新用户消息不够 5 条，跳过
    new_user_msgs = [m for m in msgs if m["role"] == "user"]
    if len(new_user_msgs) < 5:
        return {"updated": False}

    # 构建对话文本（用户消息完整，AI 消息截断）
    conversation_parts = []
    for m in msgs:
        if m["role"] == "user":
            conversation_parts.append(f"User: {m['content']}")
        else:
            name = m.get("persona_id") or "AI"
            conversation_parts.append(f"{name}: {m['content']}")
    conversation = "\n".join(conversation_parts)

    current_content = req.currentMemory or ""

    from lifee.memory.user_memory import EXTRACT_PROMPT
    prompt = EXTRACT_PROMPT.format(
        current_content=current_content,
        conversation=conversation,
    )

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        response = await provider.chat(
            messages=[Message(role=MessageRole.USER, content=prompt)],
            max_tokens=1000,
            temperature=0.2,
        )
        updated = response.content.strip()
        if not updated or updated == current_content.strip():
            return {"updated": False}

        # 写回 users.user_memory
        if req.userId:
            try:
                from lifee import store as _s
                await asyncio.to_thread(_s.user_set_memory, req.userId, updated)
            except Exception:
                pass

        # 更新 session 的最后提取 seq
        if req.sessionId and msgs:
            try:
                max_seq = max(m.get("seq", 0) for m in msgs)
                from lifee import store as _s
                await asyncio.to_thread(
                    lambda: _s.session_update(req.sessionId, last_extract_msg_count=max_seq)
                )
            except Exception:
                pass

        return {"updated": True, "memory": updated}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"updated": False, "error": str(e)}


# ---- Followup API ----

@app.post("/followup")
async def generate_followup_endpoint(req: FollowupRequest):
    """Generate a single round of structured follow-up questions without touching
    session / persona-streaming infra. Used by the home-page popup flow that
    gathers context before the chat view opens.
    """
    from lifee.debate.moderator import generate_followup as _gen
    lines = []
    for m in (req.history or []):
        if not m.content or not m.content.strip():
            continue
        if m.role == "user":
            label = "user"
        else:
            label = m.name or "assistant"
        lines.append(f"[{label}] {m.content.strip()}")
    if req.userInput and req.userInput.strip():
        lines.append(f"[user] {req.userInput.strip()}")
    transcript = "\n".join(lines) or "[user] (no input)"
    names = "、".join(
        (p.name or p.id or "").strip() for p in (req.personas or []) if (p.name or p.id)
    ) or "your guides"
    try:
        provider = _get_provider()
    except Exception as e:
        return {"data": None, "error": f"provider unavailable: {e}"}
    data = await _gen(provider, names, transcript)
    return {"data": data}


# ---- Decision API ----

@app.post("/decision")
async def decision(req: DecisionRequest, request: Request):
    """处理辩论请求 — 兼容前端的 /decision 接口"""
    # 人机验证只在登录/注册时做（AuthModal 里的 Turnstile），登录后不再拦每条消息。
    import traceback
    try:
        return await _handle_decision(req, request)
    except Exception as e:
        traceback.print_exc()
        detail = str(e) or type(e).__name__ or "unknown error"
        return {"messages": [{"personaId": "system", "text": f"Error: {detail}"}], "options": []}


async def _handle_decision(req: DecisionRequest, request: Request):
    from lifee.roles import RoleManager
    from lifee.debate.participant import Participant
    from lifee.debate.moderator import Moderator
    from lifee.debate import moderator as mod_module
    from lifee.sessions import Session

    # 检查是否请求 SSE 流式
    stream = request.query_params.get("stream") == "1"

    rm = RoleManager()
    provider = _get_provider()

    # ---- Credits 检查（登录用户 → cookie → IP） ----
    guest_uid = await _resolve_uid(request)  # Guest 的 cookie/IP uid
    if req.userId:
        uid = f"user:{req.userId}"  # 登录用户
        # Guest→注册 余额合并：首次以注册身份登录时，把 Guest 剩余余额加到注册 bonus 上
        try:
            from lifee import store as _s
            if await asyncio.to_thread(_s.credits_get, uid) is None:
                guest_bal = await _get_balance(guest_uid)
                merged = guest_bal + REGISTER_BONUS
                await asyncio.to_thread(_s.credits_set, uid, merged)
        except Exception:
            pass
    else:
        uid = guest_uid
    _need_set_cookie = not request.cookies.get(_COOKIE_NAME)
    if _need_set_cookie:
        _new_cookie_uid = str(uuid4())
    speakers = len(req.personas)
    balance = await _get_balance(uid)
    if balance < speakers:
        return {
            "messages": [{"personaId": "system", "text": "余额不足，请充值后继续。"}],
            "options": [],
            "balance": balance,
            "needsPayment": True,
        }

    # 构建问题
    question = req.userInput or req.situation or ""
    if req.context:
        question = f"{question}\n\nContext:\n{req.context}"

    # 映射角色
    participants = []
    for persona in req.personas:
        if persona.soul:
            # AI-generated persona: bypass file system entirely
            p = Participant(
                role_name=persona.id,
                provider=provider,
                role_manager=rm,
                custom_soul=persona.soul,
                custom_display_name=persona.name,
                custom_emoji=persona.emoji or "✨",
            )
        else:
            role_name = _match_role(persona.id, persona.name)
            if not role_name:
                continue
            km = _get_knowledge_manager(role_name)
            p = Participant(role_name, provider, rm, knowledge_manager=km)
            # API 端：默认关闭 tools，只在用户开启 webSearch 时保留
            if not req.webSearch:
                p.tools = []
                p.tool_executor = None
        participants.append((persona.id, p))

    if not participants:
        return JSONResponse({"messages": [{"personaId": "system", "text": "请先选择角色再开始对话。如需继续旧对话，请重新选择相同的角色。"}], "options": [], "noPersonas": True})

    # 去掉角色间延迟
    original_delay = mod_module.SPEAKER_DELAY
    mod_module.SPEAKER_DELAY = 0.5  # API 模式保留短延迟避免 rate limit

    try:
        import time
        # 清理过期会话
        now = time.time()
        expired = [k for k, v in _sessions.items() if now - v[3] > _SESSION_TTL]
        for k in expired:
            del _sessions[k]

        # 复用或新建会话
        sid = req.sessionId
        if sid and sid in _sessions:
            session, moderator_cached, participants_cached, _ = _sessions[sid]
            all_participants = [p for _, p in participants]
            moderator = moderator_cached
            # 如果参与者数量发生变化（增加/删除角色），同步更新 moderator
            if all_participants and len(all_participants) != len(moderator.participants):
                from lifee.debate.moderator import SpeakerRotation
                moderator.participants = all_participants
                moderator.rotation = SpeakerRotation(all_participants, randomize_first=True)
            _sessions[sid] = (session, moderator, participants, now)
        else:
            session = Session()
            all_participants = [p for _, p in participants]

            # 恢复对话：从 SQLite 加载历史消息到 Session
            if sid and req.userId:
                try:
                    from lifee.providers.base import MessageRole
                    from lifee import store as _s
                    db_msgs = await asyncio.to_thread(_s.msg_list, sid)
                    for m in db_msgs:
                        role = MessageRole.USER if m["role"] == "user" else MessageRole.ASSISTANT
                        name = m.get("persona_id") or None
                        session.add_message(role, m["content"], name=name)
                    if session.history:
                        print(f"[session] Restored {len(session.history)} messages for {sid[:8]}")
                except Exception as e:
                    print(f"[session] Failed to restore history: {e}")

            # 加载用户档案（user_memory）
            user_memory_context = ""
            if req.userId:
                try:
                    from lifee import store as _s
                    user_memory_context = await asyncio.to_thread(_s.user_get_memory, req.userId) or ""
                except Exception:
                    pass

            moderator = Moderator(all_participants, session, user_memory_context=user_memory_context, enable_moderator_check=req.moderator, language=req.language)
            sid = sid or str(uuid4())
            _sessions[sid] = (session, moderator, participants, now)
            # 存档：创建 chat_session（用 Supabase user ID，不是 credits uid）
            persona_names = [pid for pid, _ in participants]
            title = (req.userInput or req.situation or "New Chat")[:50]
            chat_user_id = req.userId or None
            if chat_user_id:
                await _ensure_chat_session(sid, chat_user_id, title, persona_names)

        if stream:
            # Evict stale completed generation with same sid (new user turn → new run)
            existing = _active_generations.get(sid)
            if existing and existing.done.is_set():
                _active_generations.pop(sid, None)
                existing = None

            if not existing:
                # Spawn a detached task that outlives this HTTP request
                state = _GenState()
                _active_generations[sid] = state
                gen_iter = _stream_sse(
                    moderator, participants, question, mod_module, original_delay,
                    sid, provider, session, uid, req.userId,
                    min(req.maxSpeakers, len(all_participants)) if req.maxSpeakers > 0 else 0,
                    user_input=req.userInput or "",
                )
                state.task = _asyncio.create_task(_run_generation_task(sid, state, gen_iter))

            # SSE response only observes the task's broadcast — client disconnect
            # won't cancel the task.
            resp = StreamingResponse(
                _observer_stream(sid),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
            if _need_set_cookie:
                await _migrate_balance(uid, _new_cookie_uid)
                _set_uid_cookie(resp, _new_cookie_uid)
            return resp
        else:
            # 非流式：收集所有回复后返回 JSON
            messages = []
            current_pid = ""
            current_text = ""

            chunk_count = 0
            async for participant, chunk, is_skip in moderator.run(question, max_turns=min(req.maxSpeakers, len(all_participants)) if req.maxSpeakers > 0 else len(all_participants)):
                chunk_count += 1
                if is_skip:
                    print(f"[API] skip from {participant.info.display_name}")
                    continue
                pid = _find_persona_id(participant, participants)
                if pid != current_pid:
                    if current_text:
                        messages.append({"personaId": current_pid, "text": current_text.strip()})
                    current_pid = pid
                    current_text = chunk
                else:
                    current_text += chunk

            if current_text:
                messages.append({"personaId": current_pid, "text": current_text.strip()})

            if not messages:
                messages.append({"personaId": "system", "text": f"Debug: {chunk_count} chunks, question='{question[:50]}', participants={[p.info.display_name for _, p in participants]}"})

            options = await _generate_options(provider, session)
            # 扣 credits + 存档
            seq = 0
            chat_user_id = req.userId or None
            user_text = (req.userInput or "").strip()
            if user_text and chat_user_id:
                seq += 1
                await _save_message(sid, chat_user_id, "user", user_text, seq=seq)
            for msg in messages:
                if msg.get("personaId") not in ("system", "moderator") and msg.get("text", "").strip():
                    await _deduct(uid)
                    if chat_user_id:
                        seq += 1
                        await _save_message(sid, chat_user_id, "assistant", msg["text"], persona_id=msg["personaId"], seq=seq)

            data = {"messages": messages, "options": options, "sessionId": sid, "balance": await _get_balance(uid)}
            resp = JSONResponse(data)
            if _need_set_cookie:
                await _migrate_balance(uid, _new_cookie_uid)
                _set_uid_cookie(resp, _new_cookie_uid)
            return resp

    finally:
        mod_module.SPEAKER_DELAY = original_delay


async def _generate_options(provider, session) -> list[str]:
    """用 SuggestionGenerator 生成后续选项（和 CLI 一致）"""
    from lifee.debate.suggestions import SuggestionGenerator
    sg = SuggestionGenerator(provider)
    return await sg.generate(session.get_messages())


def _find_persona_id(participant, participants_map):
    """从 participant 找到对应的前端 persona id"""
    for pid, p in participants_map:
        if p is participant or p.info.name == participant.info.name:
            return pid
    # 追问模式的虚拟 participant
    if hasattr(participant, 'info') and participant.info.name == "lifee-followup":
        return "lifee-followup"
    return "unknown"


async def _stream_sse(moderator, participants, question, mod_module=None, original_delay=None, session_id="", provider=None, session=None, uid="anonymous", chat_user_id="", max_turns=0, user_input=""):
    """生成 SSE 事件流（逐 chunk 实时推送）"""
    all_participants = [p for _, p in participants]
    current_pid = ""

    try:
      yield f"event: session\ndata: {json.dumps({'sessionId': session_id})}\n\n"
      yield ": keepalive\n\n"

      has_content = False
      current_text = ""  # 收集当前角色的完整回复
      # 从数据库获取当前最大 seq，避免多轮对话 seq 重复
      seq = 0
      if chat_user_id and session_id:
          try:
              from lifee import store as _s
              next_seq = await asyncio.to_thread(_s.msg_next_seq, session_id)
              seq = max(0, next_seq - 1)
          except Exception:
              pass

      # 存用户消息 + 日志（仅用户实际输入，不存默认 situation）
      user_text = (user_input or "").strip()
      if user_text:
          await _log_conversation(uid, "user", "", user_text)
          if chat_user_id:
              seq += 1
              await _save_message(session_id, chat_user_id, "user", user_text, seq=seq)

      import time as _time
      _turns = max_turns or len(all_participants)
      current_seq = 0               # seq of the in-flight persona row
      last_db_write = 0.0           # monotonic timestamp of last PATCH
      DB_THROTTLE_SEC = 0.3         # fire a PATCH at most every 300ms
      # Server-side emit pacing: cap visible reveal at ~30 chars/sec so the
      # frontend doesn't have to throttle. Eliminates the multi-bubble race
      # caused by frontend FIFO typewriter lagging behind backend stream.
      EMIT_CPS = 30                 # chars per second
      emit_start_ts = None          # monotonic ts when current persona started emitting
      emitted_chars = 0             # chars yielded so far for current persona
      # Fire-and-forget DB writes: never block the token stream on HTTP to Supabase.
      def _bg(coro):
          t = _asyncio.create_task(coro)
          # avoid "Task was destroyed but pending" warnings
          t.add_done_callback(lambda _t: _t.exception() if not _t.cancelled() else None)

      async def _finalize_current():
          nonlocal has_content, current_text
          if not current_pid:
              return
          if has_content:
              _bg(_deduct(uid))
              _bg(_log_conversation(uid, "assistant", current_pid, current_text.strip()))
              if chat_user_id and current_seq:
                  _bg(_patch_message_content(session_id, current_seq, current_text.strip()))

      async for participant, chunk, is_skip in moderator.run(question, max_turns=_turns):
        # Out-of-band status signal from moderator (participant=None) — forward
        # as SSE `event: status` so the frontend can swap its "Convening the
        # council" indicator for "Searching the archives" / picked speaker
        # before the first real token arrives.
        if participant is None:
            yield f"event: status\ndata: {json.dumps({'stage': chunk}, ensure_ascii=False)}\n\n"
            continue
        if is_skip:
            continue
        pid = _find_persona_id(participant, participants)
        if pid != current_pid:
            if current_pid:
                await _finalize_current()
                yield f"event: messageEnd\ndata: {json.dumps({'personaId': current_pid})}\n\n"
            current_pid = pid
            has_content = False
            current_text = ""
            last_db_write = 0.0
            emit_start_ts = None
            emitted_chars = 0
            if chat_user_id:
                seq += 1
                current_seq = seq
                _bg(_insert_message_stub(session_id, chat_user_id, "assistant", pid, current_seq))
            else:
                current_seq = 0
            yield f"event: messageStart\ndata: {json.dumps({'personaId': pid, 'seq': current_seq})}\n\n"
        if chunk and chunk.strip():
            has_content = True
        current_text += chunk
        # Pace the emit: target = (now - start) * EMIT_CPS chars cumulative
        if chunk:
            now_mono = _time.monotonic()
            if emit_start_ts is None:
                emit_start_ts = now_mono
            target_t = emit_start_ts + (emitted_chars + len(chunk)) / EMIT_CPS
            sleep_for = target_t - now_mono
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            emitted_chars += len(chunk)
        yield f"event: messageChunk\ndata: {json.dumps({'personaId': pid, 'seq': current_seq, 'chunk': chunk}, ensure_ascii=False)}\n\n"
        if chat_user_id and current_seq and has_content:
            now = _time.monotonic()
            if now - last_db_write >= DB_THROTTLE_SEC:
                last_db_write = now
                _bg(_patch_message_content(session_id, current_seq, current_text))

      if current_pid:
          await _finalize_current()
          yield f"event: messageEnd\ndata: {json.dumps({'personaId': current_pid})}\n\n"

      # 生成后续选项（追问模式时从文本解析选项，否则用 LLM 生成）
      options = []
      if current_text:
          import re
          # 解析 A. xxx / B. xxx / C. xxx 格式的选项
          parsed = re.findall(r'[A-D][.、]\s*(.+?)(?=\s+[A-D][.、]|\s*$)', current_text.replace('\n', ' '))
          if parsed and len(parsed) >= 2:
              options = [o.strip() for o in parsed if o.strip()]
      if not options and provider and session:
          options = await _generate_options(provider, session)

      # Persist options on the session so restoring it later shows the same pills
      if chat_user_id:
          async def _save_options():
              try:
                  from lifee import store as _s
                  await asyncio.to_thread(
                      lambda: _s.session_update(session_id, last_options=options)
                  )
              except Exception:
                  pass
          _bg(_save_options())

      yield f"event: options\ndata: {json.dumps({'options': options}, ensure_ascii=False)}\n\n"
      yield f"event: done\ndata: {json.dumps({'balance': await _get_balance(uid)})}\n\n"
    finally:
      if mod_module and original_delay is not None:
          mod_module.SPEAKER_DELAY = original_delay


# 静态文件：服务前端页面
_web_void_dir = Path(__file__).parent.parent / "web" / "void"
if _web_void_dir.exists():
    app.mount("/void", StaticFiles(directory=str(_web_void_dir), html=True), name="void-frontend")

_web_ui_dir = Path(__file__).parent.parent / "web" / "ui"
if _web_ui_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_ui_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
