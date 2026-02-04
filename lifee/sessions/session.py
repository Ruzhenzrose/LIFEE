"""会话模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from lifee.providers.base import Message, MessageRole


@dataclass
class Session:
    """对话会话"""

    id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: Optional[str] = None  # 当前对话的 Agent ID
    history: List[Message] = field(default_factory=list)  # 对话历史
    user_context: Dict[str, Any] = field(default_factory=dict)  # 用户背景信息
    metadata: Dict[str, Any] = field(default_factory=dict)  # 会话元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_message(self, role: MessageRole, content: str, name: Optional[str] = None):
        """添加消息到历史"""
        self.history.append(Message(role=role, content=content, name=name))
        self.updated_at = datetime.now()

    def add_user_message(self, content: str):
        """添加用户消息"""
        self.add_message(MessageRole.USER, content)

    def add_assistant_message(self, content: str, name: Optional[str] = None):
        """添加助手消息

        注意：Claude API 要求助手消息内容不能以空白字符结尾，
        因此这里会自动 rstrip() 内容。
        """
        # Claude API: "final assistant content cannot end with trailing whitespace"
        self.add_message(MessageRole.ASSISTANT, content.rstrip(), name=name)

    def get_messages(self, limit: Optional[int] = None) -> List[Message]:
        """
        获取对话历史

        Args:
            limit: 最大消息数量，None 表示全部

        Returns:
            消息列表
        """
        if limit is None:
            return self.history.copy()
        return self.history[-limit:]

    def clear_history(self):
        """清空对话历史"""
        self.history.clear()
        self.updated_at = datetime.now()

    def set_user_context(self, key: str, value: Any):
        """设置用户上下文"""
        self.user_context[key] = value
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """转换为字典格式（用于持久化）"""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "history": [msg.to_dict() for msg in self.history],
            "user_context": self.user_context,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """从字典创建会话"""
        history = [
            Message(
                role=MessageRole(msg["role"]),
                content=msg["content"],
                name=msg.get("name"),
            )
            for msg in data.get("history", [])
        ]

        return cls(
            id=data["id"],
            agent_id=data.get("agent_id"),
            history=history,
            user_context=data.get("user_context", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
