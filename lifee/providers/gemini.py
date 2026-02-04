"""Google Gemini Provider

支持 Google Gemini API (使用新的 google-genai SDK)
API 文档：https://ai.google.dev/
"""
from typing import AsyncIterator, List, Optional

from google import genai
from google.genai import types

from .base import ChatResponse, LLMProvider, Message, MessageRole, ServiceUnavailableError


class GeminiProvider(LLMProvider):
    """Google Gemini Provider"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
    ):
        """
        初始化 Gemini Provider

        Args:
            api_key: Google AI API Key
            model: 模型名称，可选：
                - gemini-2.0-flash (推荐，快速)
                - gemini-2.0-flash-thinking (推理)
                - gemini-1.5-pro (更强)
        """
        self._api_key = api_key
        self._model_name = model
        self._client = genai.Client(api_key=api_key)

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model_name

    def _convert_messages(
        self, messages: List[Message], system: Optional[str] = None
    ) -> tuple[Optional[str], List[types.Content]]:
        """
        转换消息格式为 Gemini 格式

        Gemini API 不支持 message.name 字段，把它嵌入到 content 中
        """
        system_instruction = system
        contents = []

        for msg in messages:
            # 使用 Message.format_content() 添加 XML 标签
            content = msg.format_content()
            # 防御：确保 assistant 消息不以空白结尾
            if msg.role == MessageRole.ASSISTANT:
                content = content.rstrip()

            if msg.role == MessageRole.SYSTEM:
                system_instruction = content
            elif msg.role == MessageRole.USER:
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=content)])
                )
            elif msg.role == MessageRole.ASSISTANT:
                contents.append(
                    types.Content(role="model", parts=[types.Part(text=content)])
                )

        return system_instruction, contents

    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatResponse:
        """发送聊天请求"""
        system_instruction, contents = self._convert_messages(messages, system)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=contents,
                config=config,
            )
        except Exception as e:
            # 检查是否是 503 服务不可用错误
            error_str = str(e).lower()
            if "503" in error_str or "unavailable" in error_str or "overloaded" in error_str:
                raise ServiceUnavailableError(f"Gemini 服务不可用: {e}") from e
            raise

        return ChatResponse(
            content=response.text or "",
            model=self._model_name,
            usage={
                "input_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
                "output_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
            },
            stop_reason="stop",
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
        system_instruction, contents = self._convert_messages(messages, system)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model_name,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            # 检查是否是 503 服务不可用错误
            error_str = str(e).lower()
            if "503" in error_str or "unavailable" in error_str or "overloaded" in error_str:
                raise ServiceUnavailableError(f"Gemini 服务不可用: {e}") from e
            raise
