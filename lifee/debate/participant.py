"""
辩论参与者 - 封装单个角色
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Optional

from lifee.memory import MemoryManager, format_search_results
from lifee.providers.base import LLMProvider, Message, MessageRole
from lifee.roles import RoleManager

if TYPE_CHECKING:
    from .context import DebateContext


@dataclass
class ParticipantInfo:
    """参与者信息"""
    name: str           # 角色名（目录名）
    display_name: str   # 显示名字
    emoji: str          # emoji 标识


class Participant:
    """辩论参与者 - 封装单个角色"""

    def __init__(
        self,
        role_name: str,
        provider: LLMProvider,
        role_manager: RoleManager,
        knowledge_manager: Optional[MemoryManager] = None,
    ):
        self.role_name = role_name
        self.provider = provider
        self.role_manager = role_manager
        self.knowledge_manager = knowledge_manager
        self._load_info()

    def _load_info(self):
        """加载角色的显示信息"""
        info = self.role_manager.get_role_info(self.role_name)

        self.info = ParticipantInfo(
            name=self.role_name,
            display_name=info.get("display_name", self.role_name),
            emoji=self.role_manager.get_role_emoji(self.role_name),
        )

        # 加载 system prompt
        self.system_prompt = self.role_manager.load_role(self.role_name)

    async def _search_knowledge(self, query: str) -> str:
        """搜索知识库"""
        if not self.knowledge_manager:
            return ""

        try:
            results = await self.knowledge_manager.search(
                query,
                max_results=3,
                min_score=0.35,
            )
            if results:
                return format_search_results(results)
        except Exception:
            pass
        return ""

    async def respond(
        self,
        messages: list[Message],
        user_query: str,
        debate_context: Optional[DebateContext] = None,
        user_memory_context: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        生成回应

        Args:
            messages: 完整对话历史（包含其他参与者的发言）
            user_query: 当前用户输入（用于 RAG 搜索）
            debate_context: 辩论上下文（包含其他参与者信息、轮次等）
            user_memory_context: 用户记忆上下文（跨会话记住的用户信息）

        Yields:
            流式输出的文本片段
        """
        # 1. 搜索知识库
        knowledge_context = await self._search_knowledge(user_query)

        # 2. 构建对话历史摘要（用于让分身互相“看见”）
        dialogue_context = ""
        if debate_context:
            dialogue_context = self._format_recent_dialogue(messages)

        # 3. 构建 system prompt（包含辩论上下文）
        system = self._build_system_prompt(
            knowledge_context, debate_context, user_memory_context, dialogue_context
        )

        # 4. 调用 LLM
        async for chunk in self.provider.stream(
            messages=messages,
            system=system,
            temperature=0.7,
        ):
            yield chunk

    def _build_system_prompt(
        self,
        knowledge_context: str,
        debate_context: Optional[DebateContext] = None,
        user_memory_context: Optional[str] = None,
        dialogue_context: Optional[str] = None,
    ) -> str:
        """
        构建包含知识库上下文和辩论上下文的 system prompt

        Args:
            knowledge_context: RAG 搜索结果
            debate_context: 辩论上下文（参考 clawdbot 的 extraSystemPrompt）
            user_memory_context: 用户记忆上下文
        """
        parts = [self.system_prompt]

        # 注入用户记忆上下文（放在最前面，让角色了解用户）
        if user_memory_context:
            parts.append(f"关于与你对话的用户：\n{user_memory_context}")

        # 注入辩论上下文
        if debate_context:
            parts.append(debate_context.build_context_prompt())

        # 最近对话记录（让分身明确看到其他人说了什么）
        if dialogue_context:
            parts.append(dialogue_context)

        # 知识库上下文
        if knowledge_context:
            parts.append(f"相关知识：{knowledge_context}")

        return "\n\n".join(parts)

    def _format_recent_dialogue(
        self, messages: list[Message], max_messages: int = 16, max_chars: int = 400
    ) -> str:
        """格式化最近对话记录（用于分身互相可见）"""
        if not messages:
            return ""

        recent = messages[-max_messages:]
        lines = []
        for msg in recent:
            content = msg.content.strip()
            if not content:
                continue
            if len(content) > max_chars:
                content = content[:max_chars] + "..."

            if msg.role == MessageRole.USER:
                speaker = "用户"
            else:
                speaker = msg.name or "AI"

            lines.append(f"- {speaker}: {content}")

        if not lines:
            return ""

        return "最近对话记录（按时间顺序，优先引用其中的具体内容来回应）：\n" + "\n".join(lines)
