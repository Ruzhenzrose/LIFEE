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

load_dotenv()

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

# ---- Credits 系统（Supabase 持久化） ----
GUEST_CREDITS = 6
REGISTER_BONUS = 7   # 注册奖励（叠加在 Guest 剩余余额上）
REDEEM_CREDITS = 100

_SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip('"')
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip('"')
_SB_HEADERS = {
    "apikey": _SUPABASE_KEY,
    "Authorization": f"Bearer {_SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


async def _get_balance(uid: str) -> int:
    """获取余额，新用户自动创建并给免费额度。任何外部错误都降级成初始额度，
    保证 /credits 永不 500——UI 只需要一个数字就能显示。"""
    initial = REGISTER_BONUS if uid.startswith("user:") else GUEST_CREDITS
    if not _SUPABASE_URL:
        return initial
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{uid}&select=balance",
                headers=_SB_HEADERS,
            )
            rows = r.json() if r.status_code < 400 else None
            # PostgREST 正常返回 list，错误时返回 dict — 只相信 list。
            if isinstance(rows, list):
                if rows:
                    return int(rows[0].get("balance", initial))
                # 新 uid → 插入（幂等失败不致命）
                try:
                    await c.post(
                        f"{_SUPABASE_URL}/rest/v1/user_credits",
                        headers=_SB_HEADERS,
                        json={"uid": uid, "balance": initial},
                    )
                except Exception:
                    pass
                return initial
    except Exception:
        pass
    return initial


async def _migrate_balance(from_uid: str, to_uid: str):
    """把 from_uid 的余额迁移到 to_uid（IP → cookie 迁移用）。失败静默，不阻断请求。"""
    if not _SUPABASE_URL or not from_uid:
        return
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{from_uid}&select=balance",
                headers=_SB_HEADERS,
            )
            rows = r.json() if r.status_code < 400 else None
            if not isinstance(rows, list) or not rows:
                return  # 没记录 / 错误响应 → 不迁移
            balance = int(rows[0].get("balance", 0))
            await c.post(
                f"{_SUPABASE_URL}/rest/v1/user_credits",
                headers=_SB_HEADERS,
                json={"uid": to_uid, "balance": balance},
            )
    except Exception:
        return


async def _deduct(uid: str, amount: int = 1) -> bool:
    """扣 1 credit，返回是否成功"""
    if not _SUPABASE_URL:
        return True
    import httpx
    from datetime import datetime, timezone
    bal = await _get_balance(uid)
    if bal < amount:
        return False
    async with httpx.AsyncClient() as c:
        await c.patch(
            f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{uid}",
            headers=_SB_HEADERS,
            json={"balance": bal - amount, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
    return True


async def _redeem(uid: str, code: str) -> tuple[bool, str]:
    """兑换码充值"""
    if not _SUPABASE_URL:
        return False, "no database"
    import httpx
    async with httpx.AsyncClient() as c:
        # 查找未使用的兑换码
        r = await c.get(
            f"{_SUPABASE_URL}/rest/v1/redeem_codes?code=eq.{code}&used_by=is.null&select=credits",
            headers=_SB_HEADERS,
        )
        rows = r.json()
        if not rows:
            return False, "invalid code"
        credits = rows[0]["credits"]

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # 标记已使用
        await c.patch(
            f"{_SUPABASE_URL}/rest/v1/redeem_codes?code=eq.{code}",
            headers=_SB_HEADERS,
            json={"used_by": uid, "used_at": now},
        )

        # 增加余额
        bal = await _get_balance(uid)
        await c.patch(
            f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{uid}",
            headers=_SB_HEADERS,
            json={"balance": bal + credits, "updated_at": now},
        )

        # 记录交易
        await c.post(
            f"{_SUPABASE_URL}/rest/v1/credit_transactions",
            headers=_SB_HEADERS,
            json={"uid": uid, "amount": credits, "reason": f"redeem:{code}"},
        )

        return True, f"+{credits} credits"


async def _generate_redeem_codes(n: int = 10, credits_each: int = 100) -> list[str]:
    """生成 n 个兑换码并存入数据库"""
    import secrets
    codes = []
    rows = []
    for _ in range(n):
        code = secrets.token_hex(4).upper()
        codes.append(code)
        rows.append({"code": code, "credits": credits_each})

    if _SUPABASE_URL:
        import httpx
        async with httpx.AsyncClient() as c:
            await c.post(
                f"{_SUPABASE_URL}/rest/v1/redeem_codes",
                headers=_SB_HEADERS,
                json=rows,
            )
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

    for role_name in target_roles:
        try:
            db_path = rm.get_knowledge_db_path(role_name)

            # 启动时下载，确保文件就绪
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
    """解析真实 uid：cookie 有效 → 用 cookie，否则打回 IP 池。
    伪造不存在的 cookie 不会拿到新额度。任何 Supabase 异常都降级为 IP 池。"""
    cookie_uid = request.cookies.get(_COOKIE_NAME, "")
    if cookie_uid and _SUPABASE_URL:
        # 验证 cookie uid 在数据库里是否存在
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(
                    f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{cookie_uid}&select=uid",
                    headers=_SB_HEADERS,
                )
                rows = r.json() if r.status_code < 400 else None
                if isinstance(rows, list) and rows:
                    return cookie_uid  # 合法 cookie
        except Exception:
            # 网络/DB 故障 → 信任 cookie，避免把已登录用户打回 IP 池
            return cookie_uid
        # cookie uid 不在数据库 → 伪造的，打回 IP
    elif cookie_uid:
        return cookie_uid  # 无 Supabase 时信任 cookie
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
    has_asyncio_timeout = hasattr(__import__("asyncio"), "timeout")
    sb_url = os.getenv("SUPABASE_URL", "NOT SET")
    return {
        "GOOGLE_API_KEY": key[:10] + "..." if key != "NOT SET" else key,
        "LLM_PROVIDER": provider,
        "API_LLM_PROVIDER": os.getenv("API_LLM_PROVIDER", "NOT SET"),
        "SUPABASE_URL": sb_url,
        "SUPABASE_URL_len": len(sb_url),
        "SUPABASE_URL_starts_with_quote": sb_url.startswith('"'),
        "python_version": sys.version,
        "has_asyncio_timeout": has_asyncio_timeout,
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
    """存一条消息到 Supabase（仅登录用户存完整记录）"""
    if not _SUPABASE_URL or not content.strip():
        return
    try:
        import httpx
        async with httpx.AsyncClient() as c:
            await c.post(
                f"{_SUPABASE_URL}/rest/v1/chat_messages",
                headers=_SB_HEADERS,
                json={"session_id": session_id, "user_id": user_id, "role": role,
                      "content": content, "persona_id": persona_id, "seq": seq},
            )
    except Exception:
        pass


async def _insert_message_stub(session_id: str, user_id: str, role: str, persona_id: str, seq: int):
    """Insert an empty assistant message row at the start of a persona's turn.

    Subsequent chunks PATCH this row's content. Enables Supabase Realtime clients
    (and DB refetch on reconnect) to see progressive output even if the generator
    session outlives the original SSE connection.
    """
    if not _SUPABASE_URL:
        return
    try:
        import httpx
        async with httpx.AsyncClient() as c:
            await c.post(
                f"{_SUPABASE_URL}/rest/v1/chat_messages",
                headers=_SB_HEADERS,
                json={"session_id": session_id, "user_id": user_id, "role": role,
                      "content": "", "persona_id": persona_id, "seq": seq},
            )
    except Exception:
        pass


async def _patch_message_content(session_id: str, seq: int, content: str):
    """Update the content of an in-flight message row keyed by (session_id, seq)."""
    if not _SUPABASE_URL:
        return
    try:
        import httpx
        async with httpx.AsyncClient() as c:
            await c.patch(
                f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{session_id}&seq=eq.{seq}",
                headers={**_SB_HEADERS, "Prefer": "return=minimal"},
                json={"content": content},
            )
    except Exception:
        pass


async def _log_conversation(uid: str, role: str, persona_id: str, content_preview: str):
    """简易对话日志（所有用户包括 Guest，存到 credit_transactions）"""
    if not _SUPABASE_URL:
        return
    import httpx
    preview = content_preview[:100].replace('\n', ' ')
    try:
        # 确保 uid 存在于 user_credits（外键约束）
        await _get_balance(uid)
        async with httpx.AsyncClient() as c:
            await c.post(
                f"{_SUPABASE_URL}/rest/v1/credit_transactions",
                headers=_SB_HEADERS,
                json={"uid": uid, "amount": 0, "reason": f"msg:{role}:{persona_id}:{preview}"},
            )
    except Exception:
        pass  # 日志失败不影响对话


async def _ensure_chat_session(session_id: str, user_id: str, title: str = "New Chat", personas: list = None):
    """确保 chat_session 存在，不存在则创建"""
    if not _SUPABASE_URL:
        return
    try:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}&deleted=eq.false&select=id",
                headers=_SB_HEADERS,
            )
            if not r.json():
                await c.post(
                    f"{_SUPABASE_URL}/rest/v1/chat_sessions",
                    headers=_SB_HEADERS,
                    json={"id": session_id, "user_id": user_id, "title": title,
                          "personas": personas or []},
                )
            else:
                from datetime import datetime, timezone
                await c.patch(
                    f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}",
                    headers=_SB_HEADERS,
                    json={"updated_at": datetime.now(timezone.utc).isoformat()},
                )
    except Exception:
        pass


@app.get("/sessions")
async def list_sessions(request: Request, userId: str = ""):
    """列出用户的会话"""
    if not _SUPABASE_URL or not userId:
        return {"sessions": []}
    import httpx
    async with httpx.AsyncClient() as c:
        # 获取有消息的 session（通过 inner join chat_messages）
        r = await c.get(
            f"{_SUPABASE_URL}/rest/v1/chat_sessions?user_id=eq.{userId}&deleted=eq.false&select=id,title,personas,starred,updated_at,chat_messages(id)&order=updated_at.desc&limit=20",
            headers=_SB_HEADERS,
        )
        sessions = r.json()
        # 过滤掉没有消息的空 session
        sessions = [s for s in sessions if isinstance(s, dict) and s.get("chat_messages")]
        for s in sessions:
            s.pop("chat_messages", None)
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
    if not _SUPABASE_URL:
        return {"ok": False, "message": "storage not configured"}
    import httpx
    payload = {
        "content": content,
        "email": (req.email or "").strip()[:200] or None,
        "url": (req.url or "").strip()[:500] or None,
    }
    if req.userId:
        payload["user_id"] = req.userId
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                f"{_SUPABASE_URL}/rest/v1/feedback",
                headers=_SB_HEADERS,
                json=payload,
            )
            if r.status_code not in (200, 201, 204):
                # Surface the Supabase error so the frontend can show something
                # actionable (missing table, RLS, etc).
                body = r.text[:300] if r.text else ""
                return {"ok": False, "message": f"store failed: {r.status_code} {body}"}
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
    if not _SUPABASE_URL:
        return {"hot": []}
    from datetime import datetime, timedelta, timezone
    from urllib.parse import quote
    # URL-encode so the `+00:00` offset isn't decoded as a space → PostgREST
    # returns 400 "invalid datetime" otherwise.
    cutoff = quote((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(), safe="")
    import httpx
    counts: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=10.0) as c:
        # Paginate through all sessions in window. Supabase default limit is 1000
        # per page; we bump via range headers.
        offset = 0
        page_size = 1000
        while True:
            # Note: we intentionally include deleted sessions. "Hot" is about
            # which persona people picked, not which conversations they kept.
            r = await c.get(
                f"{_SUPABASE_URL}/rest/v1/chat_sessions"
                f"?updated_at=gte.{cutoff}&select=personas",
                headers={
                    **_SB_HEADERS,
                    "Range": f"{offset}-{offset + page_size - 1}",
                    "Range-Unit": "items",
                    "Prefer": "count=exact",
                },
            )
            if r.status_code not in (200, 206):
                break
            rows = r.json() if r.content else []
            for row in rows:
                for raw in (row.get("personas") or []):
                    if not raw or raw in ("user", "system", "lifee-followup"):
                        continue
                    canonical = _canonical_persona_id(raw)
                    counts[canonical] = counts.get(canonical, 0) + 1
            if len(rows) < page_size:
                break
            offset += page_size
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:max(1, limit)]
    return {"hot": [{"id": pid, "count": n} for pid, n in ranked]}


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
    """获取会话消息 + 最新 follow-up options"""
    if not _SUPABASE_URL:
        return {"messages": [], "options": []}
    import httpx
    async with httpx.AsyncClient() as c:
        m, s = await _asyncio.gather(
            c.get(
                f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{session_id}&select=role,content,persona_id,seq,created_at&order=seq.asc",
                headers=_SB_HEADERS,
            ),
            c.get(
                f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}&select=last_options",
                headers=_SB_HEADERS,
            ),
        )
        options = []
        try:
            rows = s.json() or []
            if rows and isinstance(rows[0].get("last_options"), list):
                options = rows[0]["last_options"]
        except Exception:
            pass
        return {"messages": m.json(), "options": options}


class SessionUpdateRequest(BaseModel):
    title: str = ""
    starred: bool = None


@app.patch("/sessions/{session_id}")
async def update_session(session_id: str, req: SessionUpdateRequest):
    """更新会话（重命名/Star）"""
    if not _SUPABASE_URL:
        return {"ok": False}
    try:
        import httpx
        updates = {}
        if req.title:
            updates["title"] = req.title
        if req.starred is not None:
            updates["starred"] = req.starred
        if not updates:
            return {"ok": False, "message": "nothing to update"}
        async with httpx.AsyncClient() as c:
            await c.patch(
                f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}",
                headers=_SB_HEADERS, json=updates,
            )
        return {"ok": True}
    except Exception:
        return {"ok": False}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """软删除会话（标记 deleted=true，数据保留）"""
    if not _SUPABASE_URL:
        return {"ok": False}
    try:
        import httpx
        async with httpx.AsyncClient() as c:
            await c.patch(
                f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}",
                headers=_SB_HEADERS,
                json={"deleted": True},
            )
        return {"ok": True}
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
    if req.sessionId and _SUPABASE_URL and not msgs:
        try:
            import httpx
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{req.sessionId}&select=role,content,persona_id&order=seq.asc",
                    headers=_SB_HEADERS,
                )
                db_msgs = r.json() or []
                msgs = [{"personaId": m.get("persona_id", ""), "text": m.get("content", "")} for m in db_msgs]
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
        "Select exactly 4 persona IDs that would resonate most with this user's situation. "
        "Prioritise emotional fit first, then intellectual fit. "
        "Only use IDs from the available list. "
        'Reply ONLY with a JSON array, e.g. ["buffett","serene","rebel","drucker"]'
    )

    try:
        provider = _get_provider()
        from lifee.providers.base import Message, MessageRole
        messages = [Message(role=MessageRole.USER, content=prompt)]
        chunks = []
        async for chunk in provider.stream(messages=messages, max_tokens=80, temperature=0.3):
            chunks.append(chunk)
        text = "".join(chunks).strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "", 1).strip()
        ids = json.loads(text)
        if not isinstance(ids, list):
            raise ValueError("not a list")
        # keep only valid ids and cap at 4
        valid = [i for i in ids if i in req.persona_ids][:4]
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
        "Users share their life situations and get advice from diverse historical/fictional voices.\n\n"
        f"User situation: {req.situation.strip()}\n"
        f"Life context tags: {periods_str}\n"
        f"Already-recommended persona IDs (do NOT duplicate): {existing_str}"
        f"{search_section}\n\n"
        "Generate exactly 2 new persona definitions that would offer unique, valuable perspectives "
        "for this situation — perspectives NOT covered by typical advisors. "
        "Think beyond the obvious: consider philosophers, scientists, artists, cultural figures, "
        "fictional archetypes, or any voice that would genuinely surprise and illuminate.\n\n"
        "For each persona output:\n"
        "- id: slug like 'gen-name' (lowercase, hyphens, must start with 'gen-')\n"
        "- name: display name (English, max 25 chars)\n"
        "- role: archetype label in CAPS (max 30 chars), e.g. 'STOIC EMPEROR', 'ZEN DISRUPTOR'\n"
        "- avatar: single emoji\n"
        "- voice: one evocative sentence in their voice (max 120 chars)\n"
        "- soul: a 200-300 word system prompt defining who they are, how they think, "
        "their speech style, and what they prioritise. Write in second person ('You are...'). "
        "Make them feel vivid and distinct — not generic. "
        "They should respond in the same language as the user.\n\n"
        'Reply ONLY with a JSON array of 2 objects with keys: id, name, role, avatar, voice, soul.\n'
        'Example: [{"id":"gen-marcus","name":"Marcus Aurelius","role":"STOIC EMPEROR",'
        '"avatar":"⚔️","voice":"The obstacle is the way.","soul":"You are Marcus Aurelius..."}]'
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
    if req.sessionId and _SUPABASE_URL:
        try:
            import httpx
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{req.sessionId}&select=last_extract_msg_count",
                    headers=_SB_HEADERS,
                )
                rows = r.json() or []
                if rows:
                    last_seq = rows[0].get("last_extract_msg_count", 0) or 0
        except Exception:
            pass

    # 只加载上次提取之后的新消息
    msgs = []
    if req.sessionId and _SUPABASE_URL:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{req.sessionId}&seq=gt.{last_seq}&select=role,content,persona_id,seq&order=seq.asc",
                    headers=_SB_HEADERS,
                )
                msgs = r.json() or []
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

        # 写回 Supabase profiles
        if _SUPABASE_URL:
            try:
                import httpx
                async with httpx.AsyncClient() as c:
                    await c.patch(
                        f"{_SUPABASE_URL}/rest/v1/profiles?id=eq.{req.userId}",
                        headers=_SB_HEADERS,
                        json={"user_memory": updated},
                    )
            except Exception:
                pass

        # 更新 session 的最后提取 seq
        if req.sessionId and _SUPABASE_URL and msgs:
            try:
                max_seq = max(m.get("seq", 0) for m in msgs)
                async with httpx.AsyncClient() as c:
                    await c.patch(
                        f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{req.sessionId}",
                        headers=_SB_HEADERS,
                        json={"last_extract_msg_count": max_seq},
                    )
            except Exception:
                pass

        return {"updated": True, "memory": updated}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"updated": False, "error": str(e)}


# ---- Decision API ----

@app.post("/decision")
async def decision(req: DecisionRequest, request: Request):
    """处理辩论请求 — 兼容前端的 /decision 接口"""
    # 人机验证检查
    if not request.cookies.get("lifee_verified"):
        return JSONResponse({"needsVerification": True, "messages": [], "options": []})
    import traceback
    try:
        return await _handle_decision(req, request)
    except Exception as e:
        traceback.print_exc()
        return {"messages": [{"personaId": "system", "text": f"Error: {e}"}], "options": []}


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
        if _SUPABASE_URL:
            import httpx
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{uid}&select=balance", headers=_SB_HEADERS)
                if not r.json():
                    # user:xxx 不存在 → 首次注册，合并 Guest 余额
                    guest_bal = await _get_balance(guest_uid)
                    merged = guest_bal + REGISTER_BONUS
                    await c.post(f"{_SUPABASE_URL}/rest/v1/user_credits", headers=_SB_HEADERS, json={"uid": uid, "balance": merged})
    else:
        uid = guest_uid
    _need_set_cookie = not request.cookies.get(_COOKIE_NAME)
    if _need_set_cookie:
        _new_cookie_uid = str(uuid4())
    speakers = len([p for p in req.personas if p.id != "tarot-master"])
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
            _sessions[sid] = (session, moderator, participants, now)
        else:
            session = Session()
            all_participants = [p for _, p in participants]

            # 恢复对话：从 Supabase 加载历史消息到 Session
            if sid and _SUPABASE_URL and req.userId:
                try:
                    import httpx
                    from lifee.providers.base import MessageRole
                    async with httpx.AsyncClient() as _c:
                        _r = await _c.get(
                            f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{sid}&select=role,content,persona_id&order=seq.asc",
                            headers=_SB_HEADERS,
                        )
                        for m in _r.json() or []:
                            role = MessageRole.USER if m["role"] == "user" else MessageRole.ASSISTANT
                            name = m.get("persona_id") or None
                            session.add_message(role, m["content"], name=name)
                    if session.history:
                        print(f"[session] Restored {len(session.history)} messages for {sid[:8]}")
                except Exception as e:
                    print(f"[session] Failed to restore history: {e}")

            # 加载用户档案（user_memory）
            user_memory_context = ""
            if req.userId and _SUPABASE_URL:
                try:
                    import httpx
                    async with httpx.AsyncClient() as _c:
                        _r = await _c.get(
                            f"{_SUPABASE_URL}/rest/v1/profiles?id=eq.{req.userId}&select=user_memory",
                            headers=_SB_HEADERS,
                        )
                        rows = _r.json() or []
                        if rows and rows[0].get("user_memory"):
                            user_memory_context = rows[0]["user_memory"]
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
      if chat_user_id and session_id and _SUPABASE_URL:
          try:
              import httpx
              async with httpx.AsyncClient() as _c:
                  _r = await _c.get(
                      f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{session_id}&select=seq&order=seq.desc&limit=1",
                      headers=_SB_HEADERS,
                  )
                  _rows = _r.json()
                  if _rows and isinstance(_rows, list) and len(_rows) > 0:
                      seq = _rows[0].get("seq", 0)
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
            if chat_user_id:
                seq += 1
                current_seq = seq
                _bg(_insert_message_stub(session_id, chat_user_id, "assistant", pid, current_seq))
            else:
                current_seq = 0
            yield f"event: messageStart\ndata: {json.dumps({'personaId': pid})}\n\n"
        if chunk and chunk.strip():
            has_content = True
        current_text += chunk
        yield f"event: messageChunk\ndata: {json.dumps({'personaId': pid, 'chunk': chunk}, ensure_ascii=False)}\n\n"
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
      if chat_user_id and _SUPABASE_URL:
          async def _save_options():
              try:
                  import httpx as _hx
                  async with _hx.AsyncClient() as _c:
                      await _c.patch(
                          f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}",
                          headers={**_SB_HEADERS, "Prefer": "return=minimal"},
                          json={"last_options": options},
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
