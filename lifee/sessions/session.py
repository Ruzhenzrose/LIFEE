"""会话模型定义"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from lifee.providers.base import LLMProvider, MediaItem, Message, MessageRole


# ---- Compact 配置 ----
# DeepSeek 128K context，留 20K 给 system prompt + output
COMPACT_THRESHOLD = 100_000  # 估算 token 超过此值时触发 compact
COMPACT_KEEP_RECENT = 6      # 保留最近 N 条消息原文

COMPACT_PROMPT = """You are summarizing a multi-character discussion to save context space.

The conversation involves a user discussing life decisions with AI personas (historical figures).

Create a concise summary that preserves:
1. The user's original question and key background info
2. Each persona's core viewpoints and advice (attribute by name)
3. Key disagreements or tensions between personas
4. Any commitments or action items the user expressed
5. The current direction of the discussion

Format:
<summary>
**User's situation:** [1-2 sentences]

**Discussion so far:**
- [Persona1]: [core viewpoint in 1-2 sentences]
- [Persona2]: [core viewpoint in 1-2 sentences]
...

**Key tensions:** [if any]

**Where we left off:** [1 sentence]
</summary>

Be concise. Each persona's viewpoint should be 1-2 sentences max. Total summary should be under 500 words."""


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
    last_prompt_tokens: int = 0  # 最近一次 API 调用的 prompt token 数（精确值）

    def add_message(self, role: MessageRole, content: str, name: Optional[str] = None, media: Optional[List] = None):
        """添加消息到历史"""
        self.history.append(Message(role=role, content=content, name=name, media=media or []))
        self.updated_at = datetime.now()

    def add_user_message(self, content: str, media: Optional[List] = None):
        """添加用户消息"""
        self.add_message(MessageRole.USER, content, media=media)

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

    def update_token_count(self, prompt_tokens: int):
        """更新最近一次 API 返回的精确 prompt token 数"""
        self.last_prompt_tokens = prompt_tokens

    def estimate_tokens(self) -> int:
        """获取 token 数：优先用 API 返回的精确值，否则粗略估算"""
        if self.last_prompt_tokens > 0:
            return self.last_prompt_tokens
        # 回退：粗略估算（中文 1.5 token/字，英文 0.25 token/字符）
        total = 0
        for msg in self.history:
            for ch in msg.content:
                total += 1.5 if '\u4e00' <= ch <= '\u9fff' else 0.3
        return int(total)

    async def compact_if_needed(self, provider: LLMProvider) -> bool:
        """检查是否需要 compact，需要则执行

        Returns:
            是否执行了 compact
        """
        tokens = self.estimate_tokens()
        if tokens < COMPACT_THRESHOLD:
            return False

        print(f"[compact] Token count {tokens:,} exceeds {COMPACT_THRESHOLD:,}, compacting...")
        return await self.compact(provider)

    async def compact(self, provider: LLMProvider) -> bool:
        """压缩对话历史：旧消息 → 摘要，保留最近几条原文

        Returns:
            是否成功
        """
        if len(self.history) <= COMPACT_KEEP_RECENT:
            return False  # 消息太少，没必要压缩

        # 分割：旧消息要压缩，新消息保留
        old_messages = self.history[:-COMPACT_KEEP_RECENT]
        recent_messages = self.history[-COMPACT_KEEP_RECENT:]

        # 构建要压缩的对话文本
        conversation_text = []
        for msg in old_messages:
            role = msg.name or msg.role.value
            # 截断过长的单条消息
            content = msg.content[:2000] if len(msg.content) > 2000 else msg.content
            conversation_text.append(f"[{role}]: {content}")

        try:
            response = await provider.chat(
                messages=[
                    Message(
                        role=MessageRole.USER,
                        content=COMPACT_PROMPT + "\n\nConversation to summarize:\n\n" + "\n\n".join(conversation_text),
                    )
                ],
                max_tokens=800,
                temperature=0.2,
            )

            summary = response.content.strip()
            # 提取 <summary> 标签内容
            match = re.search(r"<summary>(.*?)</summary>", summary, re.DOTALL)
            if match:
                summary = match.group(1).strip()

            # 替换历史：摘要 + 最近消息
            compact_msg = Message(
                role=MessageRole.USER,
                content=f"[Previous conversation summary]\n{summary}",
            )
            self.history = [compact_msg] + recent_messages
            self.updated_at = datetime.now()
            return True

        except Exception as e:
            print(f"[compact] Failed: {e}")
            return False

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
        history = [Message.from_dict(msg) for msg in data.get("history", [])]

        return cls(
            id=data["id"],
            agent_id=data.get("agent_id"),
            history=history,
            user_context=data.get("user_context", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
