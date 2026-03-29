"""FallbackProvider - 带自动降级的 Provider 包装器

当主 Provider 不可用时（503、429、连接错误等），自动切换到备用 Provider。
"""
from typing import AsyncIterator, List, Optional

from .base import ChatResponse, LLMProvider, Message, RetryableError


class FallbackProvider(LLMProvider):
    """带 fallback 的 Provider 包装器

    当主 Provider 返回可重试的错误时，自动切换到下一个 Provider。

    示例：
        providers = [gemini_provider, qwen_provider, ollama_provider]
        fallback = FallbackProvider(providers)
        # 如果 Gemini 返回 503，自动使用 Qwen
    """

    def __init__(self, providers: List[LLMProvider]):
        """
        初始化 FallbackProvider

        Args:
            providers: Provider 列表，按优先级排序（第一个是主 Provider）
        """
        if not providers:
            raise ValueError("至少需要一个 Provider")
        self._providers = providers
        self._current_index = 0

    @property
    def name(self) -> str:
        return self._current.name

    @property
    def model(self) -> str:
        return self._current.model

    @property
    def _current(self) -> LLMProvider:
        """当前使用的 Provider"""
        return self._providers[self._current_index]

    def _switch_to_next(self, failed_provider: LLMProvider) -> bool:
        """切换到下一个可用的 Provider

        Args:
            failed_provider: 刚失败的 Provider

        Returns:
            True 如果成功切换，False 如果没有更多 Provider
        """
        # 找到当前 provider 在列表中的位置
        current_idx = self._providers.index(failed_provider)
        if current_idx < len(self._providers) - 1:
            self._current_index = current_idx + 1
            next_provider = self._providers[self._current_index]
            print(f"[{failed_provider.name} 不可用，切换到 {next_provider.name}]")
            return True
        return False

    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatResponse:
        """发送聊天请求，失败时自动 fallback"""
        last_error = None

        for i in range(self._current_index, len(self._providers)):
            provider = self._providers[i]
            try:
                return await provider.chat(
                    messages=messages,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
            except RetryableError as e:
                last_error = e
                if self._switch_to_next(provider):
                    continue
                else:
                    # 没有更多 Provider 了
                    raise

        # 理论上不会到这里
        if last_error:
            raise last_error
        raise RuntimeError("No providers available")

    async def stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式聊天请求，失败时自动 fallback

        注意：如果流式传输中途失败，会切换到下一个 Provider 重新开始，
        但已经输出的内容不会被清除。
        """
        last_error = None

        for i in range(self._current_index, len(self._providers)):
            provider = self._providers[i]
            try:
                async for chunk in provider.stream(
                    messages=messages,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                ):
                    yield chunk
                return  # 成功完成
            except RetryableError as e:
                last_error = e
                if self._switch_to_next(provider):
                    continue
                else:
                    # 没有更多 Provider 了
                    raise

        # 理论上不会到这里
        if last_error:
            raise last_error
        raise RuntimeError("No providers available")

    def reset(self):
        """重置到主 Provider

        在新的对话开始时调用，尝试恢复使用主 Provider。
        """
        self._current_index = 0
