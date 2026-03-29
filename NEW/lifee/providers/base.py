"""LLM Provider 抽象基类"""
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, List, Optional


# =============================================================================
# 可重试的错误类型（用于 Provider Fallback）
# =============================================================================


class RetryableError(Exception):
    """可重试的错误（应触发 fallback）"""

    pass


class ServiceUnavailableError(RetryableError):
    """服务不可用（503）"""

    pass


class RateLimitError(RetryableError):
    """速率限制（429）"""

    pass


class ConnectionError(RetryableError):
    """连接错误"""

    pass


# =============================================================================
# 消息和响应数据类
# =============================================================================


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


@dataclass
class MediaItem:
    """多媒体项（图片等）"""
    mime_type: str      # "image/jpeg" 等
    data: str           # base64 编码
    filename: str = ""  # 原始文件名

    @classmethod
    def from_file(cls, filepath: str) -> "MediaItem":
        """从文件创建"""
        path = Path(filepath).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {filepath}")

        mime_type = _MIME_MAP.get(path.suffix.lower())
        if not mime_type:
            raise ValueError(f"不支持的图片格式: {path.suffix}（支持 jpg/png/gif/webp）")

        if path.stat().st_size > MAX_IMAGE_SIZE:
            raise ValueError(f"图片太大（>{MAX_IMAGE_SIZE // 1024 // 1024}MB）: {path.name}")

        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        return cls(mime_type=mime_type, data=b64, filename=path.name)

    def to_dict(self) -> dict:
        return {"mime_type": self.mime_type, "data": self.data, "filename": self.filename}

    @classmethod
    def from_dict(cls, d: dict) -> "MediaItem":
        return cls(mime_type=d["mime_type"], data=d["data"], filename=d.get("filename", ""))


@dataclass
class Message:
    """对话消息"""
    role: MessageRole
    content: str
    name: Optional[str] = None  # 可选的发送者名称（用于多智能体）
    media: list[MediaItem] = field(default_factory=list)  # 图片等多媒体

    def to_dict(self) -> dict:
        """转换为字典格式"""
        d = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.media:
            d["media"] = [m.to_dict() for m in self.media]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        """从字典恢复"""
        media = [MediaItem.from_dict(m) for m in d.get("media", [])]
        return cls(
            role=MessageRole(d["role"]),
            content=d["content"],
            name=d.get("name"),
            media=media,
        )

    def format_content(self) -> str:
        """
        获取带 XML 标签的内容（用于多智能体对话）

        - 有 name 的消息: <msg from="name">content</msg>
        - 用户消息: <user>content</user>
        - 其他: 原内容
        """
        if self.name:
            return f'<msg from="{self.name}">{self.content}</msg>'
        elif self.role == MessageRole.USER:
            return f'<user>{self.content}</user>'
        return self.content


@dataclass
class ChatResponse:
    """聊天响应"""
    content: str
    model: str
    usage: Optional[dict] = None  # token 使用量
    stop_reason: Optional[str] = None


class LLMProvider(ABC):
    """LLM 提供商抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """当前使用的模型"""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> ChatResponse:
        """
        发送聊天请求

        Args:
            messages: 对话消息列表
            system: 系统提示词
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        流式聊天请求

        Args:
            messages: 对话消息列表
            system: 系统提示词
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            **kwargs: 其他参数

        Yields:
            str: 流式输出的文本片段
        """
        pass
