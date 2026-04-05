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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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

# CORS — allow all origins for now
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
    provider_name = (os.getenv("LLM_PROVIDER") or settings.llm_provider).lower()

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
async def root():
    index = Path(__file__).parent.parent / "web" / "ui" / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"status": "ok", "service": "LIFEE API"}


@app.get("/debug-env")
async def debug_env():
    """显示环境变量（调试用）"""
    import sys
    key = os.getenv("GOOGLE_API_KEY", "NOT SET")
    provider = os.getenv("LLM_PROVIDER", "NOT SET")
    has_asyncio_timeout = hasattr(__import__("asyncio"), "timeout")
    return {
        "GOOGLE_API_KEY": key[:10] + "..." if key != "NOT SET" else key,
        "LLM_PROVIDER": provider,
        "python_version": sys.version,
        "has_asyncio_timeout": has_asyncio_timeout,
    }


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


@app.post("/decision")
async def decision(req: DecisionRequest, request: Request):
    """处理辩论请求 — 兼容前端的 /decision 接口"""
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
            from uuid import uuid4
            session = Session()
            all_participants = [p for _, p in participants]
            moderator = Moderator(all_participants, session, enable_moderator_check=False)
            sid = sid or str(uuid4())
            _sessions[sid] = (session, moderator, participants, now)

        if stream:
            return StreamingResponse(
                _stream_sse(moderator, participants, question, mod_module, original_delay, sid),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )
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

            return {"messages": messages, "options": [], "sessionId": sid}

    finally:
        mod_module.SPEAKER_DELAY = original_delay


def _find_persona_id(participant, participants_map):
    """从 participant 找到对应的前端 persona id"""
    for pid, p in participants_map:
        if p is participant:
            return pid
    return "unknown"


async def _stream_sse(moderator, participants, question, mod_module=None, original_delay=None, session_id=""):
    """生成 SSE 事件流"""
    all_participants = [p for _, p in participants]
    current_pid = ""
    current_text = ""

    try:
      # 立即发送 sessionId 和 keepalive
      yield f"event: session\ndata: {json.dumps({'sessionId': session_id})}\n\n"
      yield ": keepalive\n\n"
      async for participant, chunk, is_skip in moderator.run(question, max_turns=len(all_participants)):
        if is_skip:
            continue
        pid = _find_persona_id(participant, participants)
        if pid != current_pid:
            if current_text:
                msg = {"personaId": current_pid, "text": current_text.strip()}
                yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            current_pid = pid
            current_text = chunk
        else:
            current_text += chunk

      if current_text:
          msg = {"personaId": current_pid, "text": current_text.strip()}
          yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

      yield f"event: options\ndata: {json.dumps({'options': []})}\n\n"
      yield f"event: done\ndata: {{}}\n\n"
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
