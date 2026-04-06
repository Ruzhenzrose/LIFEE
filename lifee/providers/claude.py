"""Claude API Provider"""
from typing import AsyncIterator, List, Optional, Union

import anthropic

from .base import ChatResponse, LLMProvider, Message, MessageRole, RateLimitError, ServiceUnavailableError


# Claude Code 版本号（用于 user-agent，需与本地安装的 claude --version 一致）
CLAUDE_CODE_VERSION = "2.1.89"

# Claude Code 计费标头（OAuth token 调用时必须作为 system 第一条，否则会被 429 限流）
CLAUDE_CODE_BILLING_HEADER = (
    f"x-anthropic-billing-header: cc_version={CLAUDE_CODE_VERSION}.72a; "
    "cc_entrypoint=cli; cch=00000;"
)


def is_oauth_token(token: str) -> bool:
    """检查是否是 OAuth token（包含 sk-ant-oat）"""
    return "sk-ant-oat" in token


class ClaudeProvider(LLMProvider):
    """Claude API 提供商"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
    ):
        """
        初始化 Claude Provider

        支持两种认证方式:
        1. API Key (sk-ant-api-...)
        2. OAuth Token (sk-ant-oat-...) - 来自 Claude Code CLI

        Args:
            api_key: Anthropic API Key 或 OAuth Token
            model: 模型名称
        """
        self._api_key = api_key
        self._model = model
        self._is_oauth = is_oauth_token(api_key)

        # 根据 token 类型选择认证方式
        if self._is_oauth:
            import uuid
            self._session_id = str(uuid.uuid4())
            # OAuth token: 模拟 Claude Code 的完整请求格式
            self._client = anthropic.AsyncAnthropic(
                api_key=None,
                auth_token=api_key,
                base_url="https://api.anthropic.com",
                default_headers={
                    "accept": "application/json",
                    "anthropic-dangerous-direct-browser-access": "true",
                    "anthropic-beta": (
                        "claude-code-20250219,oauth-2025-04-20,"
                        "interleaved-thinking-2025-05-14,"
                        "context-management-2025-06-27,"
                        "prompt-caching-scope-2026-01-05,"
                        "effort-2025-11-24"
                    ),
                    "user-agent": f"claude-cli/{CLAUDE_CODE_VERSION} (external, cli)",
                    "x-app": "cli",
                    "x-claude-code-session-id": self._session_id,
                    "x-stainless-lang": "js",
                    "x-stainless-package-version": "0.74.0",
                    "x-stainless-os": "Windows",
                    "x-stainless-arch": "x64",
                    "x-stainless-runtime": "node",
                    "x-stainless-runtime-version": "v22.17.0",
                },
            )
        else:
            # 普通 API Key
            self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def name(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_oauth(self) -> bool:
        """是否使用 OAuth token 认证"""
        return self._is_oauth

    def _convert_messages(
        self, messages: List[Message]
    ) -> tuple[Optional[str], List[dict]]:
        """
        转换消息格式为 Claude API 格式

        Claude API 需要 system 参数单独传递，不在 messages 中
        Claude API 不支持 message.name 字段，所以我们把名字嵌入到 content 中

        Returns:
            (system_prompt, messages_list)
        """
        system_prompt = None
        converted = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            else:
                # 使用 Message.format_content() 添加 XML 标签
                content = msg.format_content()
                # 防御：确保 assistant 消息不以空白结尾
                # Claude API 要求："final assistant content cannot end with trailing whitespace"
                if msg.role == MessageRole.ASSISTANT:
                    content = content.rstrip()

                if msg.media and msg.role == MessageRole.USER:
                    # 多模态消息：文本 + 图片
                    blocks = [{"type": "text", "text": content}]
                    for m in msg.media:
                        blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": m.mime_type,
                                "data": m.data,
                            },
                        })
                    converted.append({"role": msg.role.value, "content": blocks})
                else:
                    converted.append({"role": msg.role.value, "content": content})

        return system_prompt, converted

    def _build_oauth_metadata(self) -> dict:
        """构建 OAuth 请求所需的 metadata"""
        if not self._is_oauth:
            return {}
        import json
        import hashlib
        return {
            "metadata": {
                "user_id": json.dumps({
                    "device_id": hashlib.sha256(b"lifee-device").hexdigest(),
                    "account_uuid": "56eb4902-266a-4546-a57d-85ecce8dd528",
                    "session_id": self._session_id,
                })
            }
        }

    def _build_system_prompt(
        self, user_system: Optional[str]
    ) -> Union[str, List[dict]]:
        """
        构建系统提示词

        如果使用 OAuth token，必须使用特定格式声明 Claude Code 身份
        """
        if self._is_oauth:
            # OAuth token: billing header 必须是 system 的第一条
            system_blocks = [
                {
                    "type": "text",
                    "text": CLAUDE_CODE_BILLING_HEADER,
                }
            ]
            if user_system:
                # 拆分固定部分（SOUL/IDENTITY）和动态部分（RAG/对话记录）
                # 用 "## Current Conversation" 作为分界线
                parts = user_system.split("## Current Conversation", 1)
                if len(parts) == 2:
                    # 固定部分加 cache_control（SOUL + IDENTITY + skills）
                    system_blocks.append({
                        "type": "text",
                        "text": parts[0].rstrip(),
                        "cache_control": {"type": "ephemeral"},
                    })
                    # 动态部分不缓存
                    system_blocks.append({
                        "type": "text",
                        "text": "## Current Conversation" + parts[1],
                    })
                else:
                    system_blocks.append({
                        "type": "text",
                        "text": user_system,
                        "cache_control": {"type": "ephemeral"},
                    })
            return system_blocks
        else:
            # 普通 API Key: 使用字符串格式
            return user_system or ""

    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatResponse:
        """发送聊天请求"""
        msg_system, msg_list = self._convert_messages(messages)
        final_system = self._build_system_prompt(system or msg_system)

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=final_system,
                messages=msg_list,
                **self._build_oauth_metadata(),
                **kwargs,
            )
        except anthropic.RateLimitError as e:
            raise RateLimitError(f"Claude 速率��制: {e}") from e
        except anthropic.InternalServerError as e:
            raise ServiceUnavailableError(f"Claude 服务不可用: {e}") from e

        # 安���获取响应内容（防止空列表导致 IndexError）
        content = ""
        if response.content and len(response.content) > 0:
            content = response.content[0].text

        return ChatResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            stop_reason=response.stop_reason,
        )

    async def stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式聊天请求"""
        msg_system, msg_list = self._convert_messages(messages)
        final_system = self._build_system_prompt(system or msg_system)

        # 提取 tool 参数
        tools = kwargs.pop("tools", None)
        tool_executor = kwargs.pop("tool_executor", None)

        # DEBUG: 设置环境变量 LIFEE_DEBUG=1 可查看 API 调用详情
        import os
        if os.environ.get("LIFEE_DEBUG"):
            print(f"\n[CLAUDE DEBUG] model={self._model}, messages={len(msg_list)}, tools={len(tools) if tools else 0}")
            system_len = sum(len(b["text"]) for b in final_system) if isinstance(final_system, list) else len(final_system or "")
            print(f"[CLAUDE DEBUG] system_prompt_len={system_len}")
            for i, m in enumerate(msg_list):
                content_len = len(m["content"]) if isinstance(m["content"], str) else len(str(m["content"]))
                preview = (m["content"][:80].replace('\n', '\\n')) if isinstance(m["content"], str) else str(m["content"])[:80]
                print(f"[CLAUDE DEBUG] msg[{i}] role={m['role']}, len={content_len}: {preview}...")

        if tools and tool_executor:
            async for text in self._stream_with_tools(
                msg_list, final_system, tools, tool_executor,
                max_tokens, temperature, **kwargs,
            ):
                yield text
        else:
            async for text in self._stream_simple(
                msg_list, final_system, max_tokens, temperature, **kwargs,
            ):
                yield text

    async def _stream_simple(
        self, msg_list, final_system, max_tokens, temperature, **kwargs,
    ) -> AsyncIterator[str]:
        """普通流式请求（无 tool use）"""
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=final_system,
                messages=msg_list,
                **self._build_oauth_metadata(),
                **kwargs,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.RateLimitError as e:
            raise RateLimitError(f"Claude 速率限制: {e}") from e
        except anthropic.InternalServerError as e:
            raise ServiceUnavailableError(f"Claude 服务不可用: {e}") from e

    async def _stream_with_tools(
        self, msg_list, final_system, tools, tool_executor,
        max_tokens, temperature, max_rounds=5, **kwargs,
    ) -> AsyncIterator[str]:
        """带 tool use 的流式请求"""
        # 转换 ToolDefinition 为 Claude API 格式
        api_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

        messages = list(msg_list)

        for _ in range(max_rounds):
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=final_system,
                    messages=messages,
                    tools=api_tools,
                    stream=True,
                    **self._build_oauth_metadata(),
                    **kwargs,
                )
            except anthropic.RateLimitError as e:
                raise RateLimitError(f"Claude 速率限制: {e}") from e
            except anthropic.InternalServerError as e:
                raise ServiceUnavailableError(f"Claude 服务不可用: {e}") from e

            # 处理流式事件
            content_blocks = []
            current_tool_use = None
            tool_input_json = ""
            stop_reason = None

            async for event in response:
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        content_blocks.append({"type": "text", "text": ""})
                    elif event.content_block.type == "tool_use":
                        current_tool_use = {
                            "type": "tool_use",
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": {},
                        }
                        tool_input_json = ""
                        content_blocks.append(current_tool_use)

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield event.delta.text
                        if content_blocks and content_blocks[-1]["type"] == "text":
                            content_blocks[-1]["text"] += event.delta.text
                    elif event.delta.type == "input_json_delta":
                        tool_input_json += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if current_tool_use and tool_input_json:
                        import json
                        try:
                            current_tool_use["input"] = json.loads(tool_input_json)
                        except json.JSONDecodeError:
                            current_tool_use["input"] = {}
                        current_tool_use = None
                        tool_input_json = ""

                elif event.type == "message_delta":
                    stop_reason = event.delta.stop_reason

            if stop_reason != "tool_use":
                break

            # 执行工具调用
            tool_results = []
            for block in content_blocks:
                if block["type"] == "tool_use":
                    query_display = block["input"].get("query", block["name"])
                    yield f"\n🔍 搜索: {query_display}\n"
                    result = await tool_executor.execute(block["name"], block["input"])
                    # 显示搜索结果摘要（取前 3 条）
                    preview_lines = result.strip().split("\n\n")[:3]
                    for line in preview_lines:
                        first_line = line.split("\n")[0][:80]
                        yield f"  • {first_line}\n"
                    yield "\n"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result[:2000],  # 截断避免 token 爆炸
                    })

            # 扩展对话继续生成
            messages.append({"role": "assistant", "content": content_blocks})
            messages.append({"role": "user", "content": tool_results})
