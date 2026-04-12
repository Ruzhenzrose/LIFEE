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
FREE_CREDITS = 7
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
        return FREE_CREDITS  # fallback: 无 Supabase 时总是给免费额度
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{_SUPABASE_URL}/rest/v1/user_credits?uid=eq.{uid}&select=balance",
            headers=_SB_HEADERS,
        )
        rows = r.json()
        if rows:
            return rows[0]["balance"]
        # 新用户 → 插入
        r2 = await c.post(
            f"{_SUPABASE_URL}/rest/v1/user_credits",
            headers=_SB_HEADERS,
            json={"uid": uid, "balance": FREE_CREDITS},
        )
        return FREE_CREDITS


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


async def _generate_redeem_codes(n: int = 10) -> list[str]:
    """生成 n 个兑换码并存入数据库"""
    import secrets
    codes = []
    rows = []
    for _ in range(n):
        code = secrets.token_hex(4).upper()
        codes.append(code)
        rows.append({"code": code, "credits": REDEEM_CREDITS})

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

    # 直接匹配 role 目录名
    for role in available:
        if persona_id.lower() == role.lower() or persona_name.lower() == role.lower():
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
async def get_credits(request: Request, response: Response):
    """查询余额（从 cookie 读 uid，无 cookie 时用 IP）"""
    uid = await _resolve_uid(request)
    if not request.cookies.get(_COOKIE_NAME):
        # 没有 cookie → 种一个，并迁移 IP 余额
        new_uid = str(uuid4())
        await _migrate_balance(uid, new_uid)
        _set_uid_cookie(response, new_uid)
        uid = new_uid
    return {"balance": await _get_balance(uid)}


class RedeemRequest(BaseModel):
    code: str


@app.post("/credits/redeem")
async def redeem(req: RedeemRequest, request: Request):
    """兑换码充值"""
    uid = await _resolve_uid(request)
    if not uid:
        return {"ok": False, "message": "no session", "balance": 0}
    ok, msg = await _redeem(uid, req.code.strip().upper())
    return {"ok": ok, "message": msg, "balance": await _get_balance(uid)}


@app.get("/credits/generate/{n}")
async def gen_codes(n: int = 10):
    """生成兑换码（管理员用，生产环境应加鉴权）"""
    codes = await _generate_redeem_codes(n)
    return {"codes": codes}


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

    # ---- Credits 检查（cookie → IP 双重标识） ----
    uid = await _resolve_uid(request)  # 合法 cookie uid 或 "ip:x.x.x.x"
    _need_set_cookie = not request.cookies.get(_COOKIE_NAME)
    if _need_set_cookie:
        # 无 cookie → 用 IP uid 查余额，后面种 cookie 时迁移
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
        participants.append((persona.id, p))

    if not participants:
        return {"messages": [{"personaId": "system", "text": "No matching roles found."}], "options": []}

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
            moderator = Moderator(all_participants, session, enable_moderator_check=False)
            sid = sid or str(uuid4())
            _sessions[sid] = (session, moderator, participants, now)

        if stream:
            resp = StreamingResponse(
                _stream_sse(moderator, participants, question, mod_module, original_delay, sid, provider, session, uid),
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
            async for participant, chunk, is_skip in moderator.run(question, max_turns=len(all_participants)):
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
            # 扣 credits（每个有内容的角色回复 1 credit）
            for msg in messages:
                if msg.get("personaId") not in ("system", "moderator") and msg.get("text", "").strip():
                    await _deduct(uid)

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
        if p is participant:
            return pid
    return "unknown"


async def _stream_sse(moderator, participants, question, mod_module=None, original_delay=None, session_id="", provider=None, session=None, uid="anonymous"):
    """生成 SSE 事件流（逐 chunk 实时推送）"""
    all_participants = [p for _, p in participants]
    current_pid = ""

    try:
      yield f"event: session\ndata: {json.dumps({'sessionId': session_id})}\n\n"
      yield ": keepalive\n\n"

      has_content = False  # 当前角色是否有实际内容

      async for participant, chunk, is_skip in moderator.run(question, max_turns=len(all_participants)):
        if is_skip:
            continue
        pid = _find_persona_id(participant, participants)
        if pid != current_pid:
            if current_pid:
                # 上一个角色结束 → 有内容才扣钱
                if has_content:
                    await _deduct(uid)
                yield f"event: messageEnd\ndata: {json.dumps({'personaId': current_pid})}\n\n"
            current_pid = pid
            has_content = False
            yield f"event: messageStart\ndata: {json.dumps({'personaId': pid})}\n\n"
        if chunk and chunk.strip():
            has_content = True
        yield f"event: messageChunk\ndata: {json.dumps({'personaId': pid, 'chunk': chunk}, ensure_ascii=False)}\n\n"

      if current_pid:
          if has_content:
              await _deduct(uid)
          yield f"event: messageEnd\ndata: {json.dumps({'personaId': current_pid})}\n\n"

      # 生成后续选项
      options = []
      if provider and session:
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
