"""OpenAI 兼容 API Provider 基类

支持所有使用 OpenAI 兼容 API 的服务：
- Qwen (阿里通义千问)
- Ollama (本地)
- OpenCode Zen
- 等等
"""
from typing import AsyncIterator, List, Optional

import httpx
from openai import AsyncOpenAI, APIConnectionError, NotFoundError, APIStatusError

from .base import (
    ChatResponse,
    LLMProvider,
    Message,
    MessageRole,
    ServiceUnavailableError,
    RateLimitError,
    ConnectionError as BaseConnectionError,
)


class ProviderConnectionError(BaseConnectionError):
    """Provider 连接错误（可触发 fallback）"""
    pass


class ModelNotFoundError(Exception):
    """模型未找到"""
    pass


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容 API Provider 基类"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "openai-compat",
    ):
        """
        初始化 OpenAI 兼容 Provider

        Args:
            api_key: API Key
            base_url: API 端点 URL
            model: 模型名称
            provider_name: Provider 名称
        """
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._provider_name = provider_name
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model

    def _convert_messages(
        self, messages: List[Message], system: Optional[str] = None
    ) -> List[dict]:
        """
        转换消息格式

        虽然 OpenAI 支持 message.name 字段，但 Ollama/Qwen 等兼容 API 可能不支持
        为了统一处理，把 name 嵌入到 content 中
        """
        converted = []

        # 添加系统消息
        if system:
            converted.append({"role": "system", "content": system})

        for msg in messages:
            # 使用 Message.format_content() 添加 XML 标签
            content = msg.format_content()
            # 防御：确保 assistant 消息不以空白结尾
            if msg.role == MessageRole.ASSISTANT:
                content = content.rstrip()

            if msg.role == MessageRole.SYSTEM:
                converted.append({"role": "system", "content": content})
            else:
                converted.append({"role": msg.role.value, "content": content})

        return converted

    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatResponse:
        """发送聊天请求"""
        msg_list = self._convert_messages(messages, system)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=msg_list,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except (APIConnectionError, httpx.ConnectError) as e:
            if self._provider_name == "ollama":
                raise ProviderConnectionError(
                    f"无法连接到 Ollama。\n"
                    f"  如果未安装: https://ollama.ai/download\n"
                    f"  如果已安装: 请运行 'ollama serve' 启动服务"
                ) from e
            raise ProviderConnectionError(
                f"无法连接到 {self._provider_name}，请检查网络连接"
            ) from e
        except NotFoundError as e:
            if self._provider_name == "ollama":
                raise ModelNotFoundError(
                    f"模型 '{self._model}' 未找到。请先运行: ollama pull {self._model}"
                ) from e
            raise ModelNotFoundError(f"模型 '{self._model}' 未找到") from e
        except APIStatusError as e:
            # 检查 HTTP 状态码
            if e.status_code == 503:
                raise ServiceUnavailableError(
                    f"{self._provider_name} 服务不可用: {e}"
                ) from e
            if e.status_code == 429:
                raise RateLimitError(
                    f"{self._provider_name} 速率限制: {e}"
                ) from e
            raise

        choice = response.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            stop_reason=choice.finish_reason,
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
        msg_list = self._convert_messages(messages, system)

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=msg_list,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                **kwargs,
            )
        except (APIConnectionError, httpx.ConnectError) as e:
            if self._provider_name == "ollama":
                raise ProviderConnectionError(
                    f"无法连接到 Ollama。\n"
                    f"  如果未安装: https://ollama.ai/download\n"
                    f"  如果已安装: 请运行 'ollama serve' 启动服务"
                ) from e
            raise ProviderConnectionError(
                f"无法连接到 {self._provider_name}，请检查网络连接"
            ) from e
        except NotFoundError as e:
            if self._provider_name == "ollama":
                raise ModelNotFoundError(
                    f"模型 '{self._model}' 未找到。请先运行: ollama pull {self._model}"
                ) from e
            raise ModelNotFoundError(f"模型 '{self._model}' 未找到") from e
        except APIStatusError as e:
            # 检查 HTTP 状态码
            if e.status_code == 503:
                raise ServiceUnavailableError(
                    f"{self._provider_name} 服务不可用: {e}"
                ) from e
            if e.status_code == 429:
                raise RateLimitError(
                    f"{self._provider_name} 速率限制: {e}"
                ) from e
            raise

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class QwenPortalProvider(OpenAICompatProvider):
    """Qwen Portal Provider (免费 OAuth)

    完全免费，通过 OAuth 登录获取 access token
    这是 clawdbot 使用的方式
    """

    QWEN_PORTAL_BASE_URL = "https://portal.qwen.ai/v1"

    def __init__(
        self,
        access_token: str,
        model: str = "coder-model",
    ):
        """
        初始化 Qwen Portal Provider

        Args:
            access_token: Qwen Portal OAuth access token
            model: 模型名称，可选：
                - coder-model (代码模型)
                - vision-model (视觉模型)
        """
        super().__init__(
            api_key=access_token,
            base_url=self.QWEN_PORTAL_BASE_URL,
            model=model,
            provider_name="qwen-portal",
        )


class QwenProvider(OpenAICompatProvider):
    """Qwen DashScope Provider (需要 API Key)

    免费额度：2000 请求/天
    API 文档：https://help.aliyun.com/zh/model-studio/
    """

    QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-plus",
    ):
        """
        初始化 Qwen Provider

        Args:
            api_key: DashScope API Key
            model: 模型名称，可选：
                - qwen-plus (推荐，平衡性能和成本)
                - qwen-turbo (快速)
                - qwen-max (最强)
                - qwen-coder-plus (代码)
        """
        super().__init__(
            api_key=api_key,
            base_url=self.QWEN_BASE_URL,
            model=model,
            provider_name="qwen",
        )


class OllamaProvider(OpenAICompatProvider):
    """Ollama 本地 Provider

    完全免费，需要本地安装 Ollama
    安装：https://ollama.ai/
    """

    OLLAMA_BASE_URL = "http://localhost:11434/v1"

    def __init__(
        self,
        model: str = "qwen2.5",
        base_url: str = None,
    ):
        """
        初始化 Ollama Provider

        Args:
            model: 模型名称，需要先 `ollama pull <model>`
                - qwen2.5 (推荐，中文好)
                - llama3.3 (英文强)
                - deepseek-r1 (推理)
            base_url: Ollama API 地址，默认 localhost:11434
        """
        super().__init__(
            api_key="ollama",  # Ollama 不需要真正的 API Key
            base_url=base_url or self.OLLAMA_BASE_URL,
            model=model,
            provider_name="ollama",
        )


class OpenCodeZenProvider(OpenAICompatProvider):
    """OpenCode Zen Provider

    多模型代理服务，GLM-4.7 模型免费
    API 端点与 clawdbot 一致
    """

    OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4.7",
    ):
        """
        初始化 OpenCode Zen Provider

        Args:
            api_key: OpenCode API Key
            model: 模型名称 (glm-4.7 免费，其他需要 $200/月订阅)
        """
        super().__init__(
            api_key=api_key,
            base_url=self.OPENCODE_BASE_URL,
            model=model,
            provider_name="opencode-zen",
        )
