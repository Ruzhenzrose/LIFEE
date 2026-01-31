"""
辩论参与者 - 封装单个角色
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Optional

from lifee.memory import MemoryManager, format_search_results
from lifee.providers.base import LLMProvider, Message
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
    ) -> AsyncIterator[str]:
        """
        生成回应

        Args:
            messages: 完整对话历史（包含其他参与者的发言）
            user_query: 当前用户输入（用于 RAG 搜索）
            debate_context: 辩论上下文（包含其他参与者信息、轮次等）

        Yields:
            流式输出的文本片段
        """
        # 1. 搜索知识库
        knowledge_context = await self._search_knowledge(user_query)

        # 2. 构建 system prompt（包含辩论上下文）
        system = self._build_system_prompt(knowledge_context, debate_context)

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
    ) -> str:
        """
        构建包含知识库上下文和辩论上下文的 system prompt

        Args:
            knowledge_context: RAG 搜索结果
            debate_context: 辩论上下文（参考 clawdbot 的 extraSystemPrompt）
        """
        parts = [self.system_prompt]

        # 注入辩论上下文（类似 clawdbot 的 extraSystemPrompt 机制）
        if debate_context:
            parts.append("---")
            parts.append(debate_context.build_context_prompt())
        else:
            # 兼容旧的调用方式（无 debate_context）
            fallback_context = f"""---

## 多角度讨论规则

你正在参与一场多角度讨论。你是 {self.info.display_name}。

- **保持人格**：始终保持你的思考方式和说话风格
- **回应他人**：你可以回应对话中其他参与者的观点，用你自己的视角
- **不同意见**：你可以提出不同意见，这正是讨论的意义
- **有实质内容**：回应要有深度，避免泛泛而谈
- **简洁有力**：控制回复长度，留给其他参与者空间"""
            parts.append(fallback_context)

        # 知识库上下文
        if knowledge_context:
            parts.append(f"""---

## 相关知识（供参考）

{knowledge_context}""")

        return "\n\n".join(parts)
