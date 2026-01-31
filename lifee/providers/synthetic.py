"""Synthetic Provider

完全免费的 AI 模型代理服务
API 端点: https://api.synthetic.new/anthropic
使用 Anthropic Messages API 格式
"""
from typing import AsyncIterator, List, Optional

import anthropic

from .base import ChatResponse, LLMProvider, Message, MessageRole


# Synthetic 支持的免费模型
SYNTHETIC_MODELS = {
    # 默认模型
    "minimax-m2.1": "hf:MiniMaxAI/MiniMax-M2.1",
    # GLM 系列
    "glm-4.5": "hf:zai-org/GLM-4.5",
    "glm-4.6": "hf:zai-org/GLM-4.6",
    "glm-4.7": "hf:zai-org/GLM-4.7",
    # DeepSeek 系列
    "deepseek-r1": "hf:deepseek-ai/DeepSeek-R1-0528",
    "deepseek-v3": "hf:deepseek-ai/DeepSeek-V3",
    "deepseek-v3.1": "hf:deepseek-ai/DeepSeek-V3.1",
    "deepseek-v3.2": "hf:deepseek-ai/DeepSeek-V3.2",
    # Qwen 系列
    "qwen3-235b": "hf:Qwen/Qwen3-235B-A22B-Instruct-2507",
    "qwen3-coder": "hf:Qwen/Qwen3-Coder-480B-A35B-Instruct",
    "qwen3-thinking": "hf:Qwen/Qwen3-235B-A22B-Thinking-2507",
    # Kimi
    "kimi-k2": "hf:moonshotai/Kimi-K2-Instruct-0905",
    "kimi-k2-thinking": "hf:moonshotai/Kimi-K2-Thinking",
    # Llama
    "llama-3.3": "hf:meta-llama/Llama-3.3-70B-Instruct",
    "llama-4": "hf:meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
}


class SyntheticProvider(LLMProvider):
    """Synthetic Provider - 完全免费的 AI 模型服务

    支持的模型别名:
    - minimax-m2.1 (默认)
    - glm-4.5, glm-4.6, glm-4.7
    - deepseek-r1, deepseek-v3, deepseek-v3.1, deepseek-v3.2
    - qwen3-235b, qwen3-coder, qwen3-thinking
    - kimi-k2, kimi-k2-thinking
    - llama-3.3, llama-4
    """

    SYNTHETIC_BASE_URL = "https://api.synthetic.new/anthropic"

    def __init__(
        self,
        api_key: str = "synthetic",
        model: str = "deepseek-v3",
    ):
        """
        初始化 Synthetic Provider

        Args:
            api_key: API Key (可选，Synthetic 可能不需要真正的 key)
            model: 模型名称或别名
        """
        self._api_key = api_key
        # 解析模型别名
        model_lower = model.lower()
        self._model = SYNTHETIC_MODELS.get(model_lower, model)
        self._model_alias = model_lower

        # 使用 Anthropic SDK，但指向 Synthetic 端点
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=self.SYNTHETIC_BASE_URL,
        )

    @property
    def name(self) -> str:
        return "synthetic"

    @property
    def model(self) -> str:
        return self._model_alias

    def _convert_messages(
        self, messages: List[Message]
    ) -> tuple[Optional[str], List[dict]]:
        """
        转换消息格式

        Synthetic 使用 Anthropic API 格式，不支持 message.name 字段
        把 name 嵌入到 content 中
        """
        system_prompt = None
        converted = []

        for msg in messages:
            # 使用 Message.format_content() 添加 XML 标签
            content = msg.format_content()
            # 防御：确保 assistant 消息不以空白结尾
            if msg.role == MessageRole.ASSISTANT:
                content = content.rstrip()

            if msg.role == MessageRole.SYSTEM:
                system_prompt = content
            else:
                converted.append({"role": msg.role.value, "content": content})

        return system_prompt, converted

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
        final_system = system or msg_system or ""

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=final_system,
            messages=msg_list,
        )

        return ChatResponse(
            content=response.content[0].text,
            model=self._model_alias,
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
        final_system = system or msg_system or ""

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=final_system,
            messages=msg_list,
        ) as stream:
            async for text in stream.text_stream:
                yield text
