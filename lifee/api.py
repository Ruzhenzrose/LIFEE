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


async def _moderator_check(provider, question: str) -> str | None:
    """主持人预审：判断用户输入是否需要补充信息。

    返回追问文本（需要补充时），或 None（信息已充分）。
    """
    from lifee.providers.base import Message, MessageRole

    prompt = """你是一场深度讨论的主持人。用户刚提出了一个问题，你需要判断：这个问题的背景信息是否足够让专家们给出有针对性的建议？

用户的问题：
{question}

判断规则：
- 如果问题已经足够具体（包含了关键背景），直接输出 PASS
- 如果缺少关键信息导致专家们只能泛泛而谈，生成 2-3 个温和自然的追问

如果需要追问，请用以下格式（中文）：
- 语气温和、像朋友聊天，不要像问卷调查
- 每个问题给出 2-3 个选项，让用户轻松选择
- 不要超过 3 个问题
- 开头用一句话自然过渡，比如"想更好地帮你分析，能先聊几个小问题吗？"

示例格式：
想更好地帮你分析，能先聊几个小问题吗？

1. 你目前大概处于什么阶段？
   A. 刚毕业/工作1-2年  B. 工作3-5年  C. 5年以上

2. 你最在意的是什么？
   A. 收入和稳定  B. 成长和学习  C. 自由和生活质量

如果问题已经足够具体，只输出：PASS""".format(question=question)

    try:
        response = await provider.chat(
            messages=[Message(role=MessageRole.USER, content=prompt)],
            max_tokens=400,
            temperature=0.3,
        )
        result = response.content.strip()
        if result.upper().startswith("PASS"):
            return None
        return result
    except Exception:
        return None  # 出错时不阻塞，直接进入辩论


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

    # ---- 主持人预审：判断是否需要向用户追问 ----
    if req.moderator and question and not req.context:
        clarification = await _moderator_check(provider, question)
        if clarification:
            return {"messages": [{"personaId": "moderator", "text": clarification}], "options": [], "needsClarification": True}

    # 映射角色
    participants = []
    for persona in req.personas:
        role_name = _match_role(persona.id, persona.name)
        if not role_name:
            continue
        # Skip knowledge manager in API mode — knowledge.db doesn't exist on Render
        # and rebuilding it per-request adds 20+ seconds of Gemini embedding calls
        p = Participant(role_name, provider, rm, knowledge_manager=None)
        participants.append((persona.id, p))

    if not participants:
        return {"messages": [{"personaId": "system", "text": "No matching roles found."}], "options": []}

    # 去掉角色间延迟
    original_delay = mod_module.SPEAKER_DELAY
    mod_module.SPEAKER_DELAY = 0.5  # API 模式保留短延迟避免 rate limit

    try:
        session = Session()
        all_participants = [p for _, p in participants]
        moderator = Moderator(all_participants, session)

        if stream:
            return StreamingResponse(
                _stream_sse(moderator, participants, question, mod_module, original_delay),
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

            return {"messages": messages, "options": []}

    finally:
        mod_module.SPEAKER_DELAY = original_delay


def _find_persona_id(participant, participants_map):
    """从 participant 找到对应的前端 persona id"""
    for pid, p in participants_map:
        if p is participant:
            return pid
    return "unknown"


async def _stream_sse(moderator, participants, question, mod_module=None, original_delay=None):
    """生成 SSE 事件流"""
    all_participants = [p for _, p in participants]
    current_pid = ""
    current_text = ""

    try:
      # 立即发送注释保持连接
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
