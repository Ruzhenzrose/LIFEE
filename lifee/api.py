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

# 知识库管理器缓存：role_name → MemoryManager
_knowledge_managers: dict = {}
_km_initialized = False

# 会话缓存：session_id → (Session, Moderator, participants, last_access_time)
_sessions: dict = {}
_SESSION_TTL = 3600  # 1小时过期

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
    """获取余额，新用户自动创建并给免费额度"""
    if not _SUPABASE_URL:
        return REGISTER_BONUS if uid.startswith("user:") else GUEST_CREDITS
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{uid}&select=balance",
            headers=_SB_HEADERS,
        )
        rows = r.json()
        if rows:
            return rows[0]["balance"]
        # 新用户 → 插入（注册用户只给 bonus，Guest 给完整额度）
        initial = REGISTER_BONUS if uid.startswith("user:") else GUEST_CREDITS
        await c.post(
            f"{_SUPABASE_URL}/rest/v1/user_credits",
            headers=_SB_HEADERS,
            json={"uid": uid, "balance": initial},
        )
        return initial


async def _migrate_balance(from_uid: str, to_uid: str):
    """把 from_uid 的余额迁移到 to_uid（IP → cookie 迁移用）"""
    if not _SUPABASE_URL or not from_uid:
        return
    import httpx
    async with httpx.AsyncClient() as c:
        # 查 from_uid 是否有记录
        r = await c.get(
            f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{from_uid}&select=balance",
            headers=_SB_HEADERS,
        )
        rows = r.json()
        if not rows:
            return  # IP 没用过，不需要迁移
        balance = rows[0]["balance"]
        # 创建 to_uid 继承余额
        await c.post(
            f"{_SUPABASE_URL}/rest/v1/user_credits",
            headers=_SB_HEADERS,
            json={"uid": to_uid, "balance": balance},
        )


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
    """启动时从 GitHub Release 下载预构建的知识库"""
    global _km_initialized
    if _km_initialized:
        return
    _km_initialized = True

    from lifee.roles import RoleManager
    from lifee.memory import MemoryManager, create_embedding_provider

    rm = RoleManager()

    # 确定要加载哪些角色
    priority_roles = os.getenv("RAG_ROLES", ",".join(_RELEASE_DBS)).split(",")
    target_roles = [r.strip() for r in priority_roles if r.strip()]

    # embedding provider（用于搜索时生成 query embedding）
    google_key = os.getenv("GOOGLE_API_KEY", "")
    if not google_key:
        print("[knowledge] No GOOGLE_API_KEY, skipping RAG")
        return

    try:
        embedding = create_embedding_provider(google_api_key=google_key)
    except Exception as e:
        print(f"[knowledge] Failed to create embedding provider: {e}")
        return

    for role_name in target_roles:
        try:
            db_path = rm.get_knowledge_db_path(role_name)

            # db 不存在且在 Release 上有 → 下载
            if not db_path.exists() and role_name in _RELEASE_DBS:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                if not _download_db(role_name, db_path):
                    continue

            if db_path.exists():
                role_info = rm.get_role_info(role_name)
                knowledge_lang = role_info.get("knowledge_lang", "English")
                km = MemoryManager(db_path, embedding, knowledge_lang=knowledge_lang)
                stats = km.get_stats()
                count = stats.get("chunk_count", 0)
                if count > 0:
                    _knowledge_managers[role_name] = km
                    print(f"[knowledge] {role_name}: {count} chunks")
        except Exception as e:
            print(f"[knowledge] {role_name}: failed ({e})")

    print(f"[knowledge] Loaded {len(_knowledge_managers)} roles with RAG")


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
    伪造不存在的 cookie 不会拿到新额度。"""
    cookie_uid = request.cookies.get(_COOKIE_NAME, "")
    if cookie_uid and _SUPABASE_URL:
        # 验证 cookie uid 在数据库里是否存在
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{cookie_uid}&select=uid",
                headers=_SB_HEADERS,
            )
            if r.json():
                return cookie_uid  # 合法 cookie
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


class DecisionRequest(BaseModel):
    situation: str = ""
    userInput: str = ""
    personas: list[PersonaInput] = []
    context: str = ""
    moderator: bool = True  # 主持人预审开关，默认开启
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
                f"{_SUPABASE_URL}/rest/v1/chat_sessions?id=eq.{session_id}&select=id",
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


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取会话消息"""
    if not _SUPABASE_URL:
        return {"messages": []}
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{_SUPABASE_URL}/rest/v1/chat_messages?session_id=eq.{session_id}&select=role,content,persona_id,seq,created_at&order=seq.asc",
            headers=_SB_HEADERS,
        )
        return {"messages": r.json()}


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
        role_name = _match_role(persona.id, persona.name)
        if not role_name:
            continue
        km = _knowledge_managers.get(role_name)
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
            moderator = Moderator(all_participants, session, enable_moderator_check=False, language=req.language)
            sid = sid or str(uuid4())
            _sessions[sid] = (session, moderator, participants, now)
            # 存档：创建 chat_session（用 Supabase user ID，不是 credits uid）
            persona_names = [pid for pid, _ in participants]  # 存前端 persona id，不是 display name
            title = (req.userInput or req.situation or "New Chat")[:50]
            chat_user_id = req.userId or None  # Supabase UUID
            if chat_user_id:
                await _ensure_chat_session(sid, chat_user_id, title, persona_names)

        if stream:
            resp = StreamingResponse(
                _stream_sse(moderator, participants, question, mod_module, original_delay, sid, provider, session, uid, req.userId, min(req.maxSpeakers, len(all_participants)) if req.maxSpeakers > 0 else 0),
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
            question_text = req.userInput or req.situation or ""
            chat_user_id = req.userId or None
            if question_text and chat_user_id:
                seq += 1
                await _save_message(sid, chat_user_id, "user", question_text, seq=seq)
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


async def _stream_sse(moderator, participants, question, mod_module=None, original_delay=None, session_id="", provider=None, session=None, uid="anonymous", chat_user_id="", max_turns=0):
    """生成 SSE 事件流（逐 chunk 实时推送）"""
    all_participants = [p for _, p in participants]
    current_pid = ""

    try:
      yield f"event: session\ndata: {json.dumps({'sessionId': session_id})}\n\n"
      yield ": keepalive\n\n"

      has_content = False
      current_text = ""  # 收集当前角色的完整回复
      seq = 0

      # 存档用户消息（仅登录用户） + 日志（所有用户）
      if question:
          await _log_conversation(uid, "user", "", question)
          if chat_user_id:
              seq += 1
              await _save_message(session_id, chat_user_id, "user", question, seq=seq)

      _turns = max_turns or len(all_participants)
      async for participant, chunk, is_skip in moderator.run(question, max_turns=_turns):
        if is_skip:
            continue
        pid = _find_persona_id(participant, participants)
        if pid != current_pid:
            if current_pid:
                if has_content:
                    await _deduct(uid)
                    await _log_conversation(uid, "assistant", current_pid, current_text.strip())
                    if chat_user_id:
                        seq += 1
                        await _save_message(session_id, chat_user_id, "assistant", current_text.strip(), persona_id=current_pid, seq=seq)
                yield f"event: messageEnd\ndata: {json.dumps({'personaId': current_pid})}\n\n"
            current_pid = pid
            has_content = False
            current_text = ""
            yield f"event: messageStart\ndata: {json.dumps({'personaId': pid})}\n\n"
        if chunk and chunk.strip():
            has_content = True
        current_text += chunk
        yield f"event: messageChunk\ndata: {json.dumps({'personaId': pid, 'chunk': chunk}, ensure_ascii=False)}\n\n"

      if current_pid:
          if has_content:
              await _deduct(uid)
              await _log_conversation(uid, "assistant", current_pid, current_text.strip())
              if chat_user_id:
                  seq += 1
                  await _save_message(session_id, chat_user_id, "assistant", current_text.strip(), persona_id=current_pid, seq=seq)
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

      yield f"event: options\ndata: {json.dumps({'options': options}, ensure_ascii=False)}\n\n"
      yield f"event: done\ndata: {json.dumps({'balance': await _get_balance(uid)})}\n\n"
    finally:
      if mod_module and original_delay is not None:
          mod_module.SPEAKER_DELAY = original_delay


# 静态文件：服务前端页面
_web_ui_dir = Path(__file__).parent.parent / "web" / "ui"
if _web_ui_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_ui_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
