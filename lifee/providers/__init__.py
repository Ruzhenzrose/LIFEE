"""LLM Providers"""
from .base import (
    ChatResponse,
    LLMProvider,
    Message,
    MessageRole,
    RetryableError,
    ServiceUnavailableError,
    RateLimitError,
    ConnectionError,
)
from .claude import ClaudeProvider
from .openai_compat import QwenPortalProvider, QwenProvider, OllamaProvider, OpenCodeZenProvider, ProviderConnectionError, ModelNotFoundError
from .gemini import GeminiProvider
from .synthetic import SyntheticProvider
from .fallback import FallbackProvider
from .auth import (
    OAuthCredentials,
    read_claude_code_credentials,
    read_clawdbot_qwen_credentials,
    read_clawdbot_synthetic_credentials,
    get_api_key_from_credentials,
    get_auth_info,
)

__all__ = [
    # 基类
    "LLMProvider",
    "Message",
    "MessageRole",
    "ChatResponse",
    # Providers
    "ClaudeProvider",
    "QwenPortalProvider",
    "QwenProvider",
    "OllamaProvider",
    "OpenCodeZenProvider",
    "GeminiProvider",
    "SyntheticProvider",
    "FallbackProvider",
    # 异常
    "RetryableError",
    "ServiceUnavailableError",
    "RateLimitError",
    "ConnectionError",
    "ProviderConnectionError",
    "ModelNotFoundError",
    # 认证
    "OAuthCredentials",
    "read_claude_code_credentials",
    "read_clawdbot_qwen_credentials",
    "read_clawdbot_synthetic_credentials",
    "get_api_key_from_credentials",
    "get_auth_info",
]
