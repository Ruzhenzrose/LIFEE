"""Claude API Provider"""
from typing import AsyncIterator, List, Optional, Union

import anthropic

from .base import ChatResponse, LLMProvider, Message, MessageRole


# Claude Code 版本号（用于 user-agent）
CLAUDE_CODE_VERSION = "2.1.2"

# Claude Code 身份声明（使用 OAuth token 时必须包含）
CLAUDE_CODE_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."


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
            # OAuth token: 模拟 Claude Code 的完整配置
            self._client = anthropic.AsyncAnthropic(
                api_key=None,
                auth_token=api_key,
                default_headers={
                    "accept": "application/json",
                    "anthropic-dangerous-direct-browser-access": "true",
                    "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,fine-grained-tool-streaming-2025-05-14,interleaved-thinking-2025-05-14",
                    "user-agent": f"claude-cli/{CLAUDE_CODE_VERSION} (external, cli)",
                    "x-app": "cli",
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
                # Claude API 不支持 name 字段，用 XML 标签标记发言者
                # 使用 XML 而非 [name]: 前缀，因为 LLM 不易模仿 XML 结构
                content = msg.content
                if msg.name:
                    content = f'<msg from="{msg.name}">{content}</msg>'
                # 防御：确保 assistant 消息不以空白结尾（必须在添加 name 前缀之后）
                # 因为 f"[name]: {empty_content}" 会产生 "[name]: " 以空格结尾
                # Claude API 要求："final assistant content cannot end with trailing whitespace"
                if msg.role == MessageRole.ASSISTANT:
                    content = content.rstrip()
                converted.append({"role": msg.role.value, "content": content})

        return system_prompt, converted

    def _build_system_prompt(
        self, user_system: Optional[str]
    ) -> Union[str, List[dict]]:
        """
        构建系统提示词

        如果使用 OAuth token，必须使用特定格式声明 Claude Code 身份
        """
        if self._is_oauth:
            # OAuth token: 使用数组格式，包含 cache_control
            system_blocks = [
                {
                    "type": "text",
                    "text": CLAUDE_CODE_IDENTITY,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            if user_system:
                system_blocks.append({"type": "text", "text": user_system})
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

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=final_system,
            messages=msg_list,
            **kwargs,
        )

        return ChatResponse(
            content=response.content[0].text,
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

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=final_system,
            messages=msg_list,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text
