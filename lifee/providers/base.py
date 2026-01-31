"""LLM Provider 抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, List, Optional


class MessageRole(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """对话消息"""
    role: MessageRole
    content: str
    name: Optional[str] = None  # 可选的发送者名称（用于多智能体）

    def to_dict(self) -> dict:
        """转换为字典格式"""
        d = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d

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
