"""
辩论参与者 - 封装单个角色
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Optional

from lifee.memory import MemoryManager, format_search_results
from lifee.memory.search import SearchResult
from lifee.providers.base import LLMProvider, Message
from lifee.roles import RoleManager
from lifee.roles.skills import SkillSet

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
        self.skill_set: SkillSet = role_manager.load_skills(role_name)
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

    async def _search_knowledge(self, query: str) -> list[SearchResult]:
        """搜索知识库，返回原始结果（供 RAG 注入和技能匹配）"""
        if not self.knowledge_manager:
            return []

        try:
            return await self.knowledge_manager.search(
                query,
                max_results=3,
                min_score=0.35,
            )
        except Exception:
            return []

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
        knowledge_results = await self._search_knowledge(user_query)
        knowledge_context = format_search_results(knowledge_results)

        # 2. 基于 RAG 结果匹配触发技能 (Tier 2)
        triggered_context = ""
        if self.skill_set.triggered_skills and knowledge_results:
            matched = self.skill_set.match_by_results(knowledge_results)
            if matched:
                triggered_context = "\n\n".join(s.content for s in matched)

        # 3. 构建 system prompt（包含辩论上下文）
        system = self._build_system_prompt(
            knowledge_context, debate_context, user_memory_context,
            triggered_context,
        )

        # 3. 调用 LLM
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
        triggered_skill_context: str = "",
    ) -> str:
        """
        构建包含知识库上下文和辩论上下文的 system prompt

        注入顺序:
        1. 角色定义 (SOUL + IDENTITY + core skills)
        2. 触发技能 (Tier 2, 基于 RAG 结果)
        3. 用户记忆
        4. 辩论上下文
        5. RAG 知识库 (Tier 3)
        """
        parts = [self.system_prompt]

        # 注入触发技能 (Tier 2)
        if triggered_skill_context:
            parts.append(triggered_skill_context)

        # 注入用户记忆上下文
        if user_memory_context:
            parts.append(f"关于与你对话的用户：\n{user_memory_context}")

        # 注入辩论上下文
        if debate_context:
            parts.append(debate_context.build_context_prompt())

        # 知识库上下文 (Tier 3)
        if knowledge_context:
            parts.append(f"相关知识：{knowledge_context}")

        return "\n\n".join(parts)
