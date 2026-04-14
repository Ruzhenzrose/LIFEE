"""
辩论参与者 - 封装单个角色
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Optional

from lifee.memory import MemoryManager, format_search_results
from lifee.memory.search import SearchResult
from lifee.providers.base import LLMProvider, Message, MessageRole
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
        self._load_tools()

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

    def _load_tools(self):
        """加载角色配置的工具"""
        info = self.role_manager.get_role_info(self.role_name)
        tool_names = info.get("tools", [])
        if tool_names:
            from lifee.tools import get_tool_definitions, DefaultToolExecutor
            self.tools = get_tool_definitions(tool_names)
            self.tool_executor = DefaultToolExecutor()
        else:
            self.tools = []
            self.tool_executor = None

    async def _search_knowledge(
        self, query: str, translated_keywords: str = ""
    ) -> list[SearchResult]:
        """搜索知识库，返回原始结果（供 RAG 注入和技能匹配）"""
        if not self.knowledge_manager:
            return []

        try:
            return await self.knowledge_manager.search(
                query,
                max_results=3,
                min_score=0.35,
                keyword_query_override=translated_keywords or None,
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
        # 0. 跨语言关键词翻译（复用于 RAG 搜索和 Tier 2 技能匹配）
        translated_keywords = ""
        if self.knowledge_manager and user_query:
            from lifee.memory.embeddings import GeminiEmbedding
            emb = self.knowledge_manager.embedding
            if isinstance(emb, GeminiEmbedding):
                translated_keywords = await emb.translate_to_keywords(
                    user_query, self.knowledge_manager.knowledge_lang
                )

        # 1. 搜索知识库（传入已翻译的关键词，避免重复翻译）
        knowledge_results = await self._search_knowledge(
            user_query, translated_keywords
        )
        knowledge_context = format_search_results(knowledge_results)

        # 2. 基于用户输入匹配触发技能 (Tier 2)
        triggered_context = ""
        if self.skill_set.triggered_skills and user_query:
            matched = self.skill_set.match_by_input(user_query, translated_keywords)
            if matched:
                triggered_context = "\n\n".join(s.content for s in matched)

        # 3. 投资角色：用户提到股票/商品/加密货币时自动获取实时数据
        stock_data_context = ""
        if user_query and self.skill_set.triggered_skills:
            inv_skills = {"business_analysis", "financial_statements", "valuation_math"}
            role_skill_names = {s.name for s in self.skill_set.triggered_skills}
            if inv_skills & role_skill_names:
                from lifee.market import resolve_and_fetch
                stock_data_context = await resolve_and_fetch(user_query, translated_keywords)

        # 4. 构建对话历史摘要（用于让分身互相"看见"）
        dialogue_context = ""
        if debate_context:
            dialogue_context = self._format_recent_dialogue(messages)

        # 5. 构建 system prompt（包含辩论上下文）
        system = self._build_system_prompt(
            knowledge_context, debate_context, user_memory_context,
            triggered_context, dialogue_context, stock_data_context,
        )

        # 6. 重映射消息角色：只有自己之前的发言保持 assistant，其他角色的发言转为 user
        my_name = self.info.display_name
        remapped = []
        for msg in messages:
            if msg.role == MessageRole.ASSISTANT and msg.name != my_name:
                # 其他角色的发言 → user（模型会去"回应"而非"延续"）
                remapped.append(Message(
                    role=MessageRole.USER,
                    content=msg.content,
                    name=msg.name,
                    media=msg.media,
                ))
            else:
                remapped.append(msg)

        # 7. 调用 LLM
        extra_kwargs = {}
        if self.tools and self.tool_executor:
            extra_kwargs["tools"] = self.tools
            extra_kwargs["tool_executor"] = self.tool_executor

        async for chunk in self.provider.stream(
            messages=remapped,
            system=system,
            temperature=0.7,
            **extra_kwargs,
        ):
            yield chunk

    def _build_system_prompt(
        self,
        knowledge_context: str,
        debate_context: Optional[DebateContext] = None,
        user_memory_context: Optional[str] = None,
        triggered_skill_context: str = "",
        dialogue_context: Optional[str] = None,
        stock_data_context: str = "",
    ) -> str:
        """
        构建包含知识库上下文和辩论上下文的 system prompt

        注入顺序：
        1. 角色定义 (SOUL + IDENTITY + core skills)
        2. 触发技能 (Tier 2, 基于用户输入)
        3. 实时市场数据（仅投资技能触发时）
        4. 用户记忆
        5. 辩论上下文
        6. 最近对话记录
        7. RAG 知识库
        """
        parts = [self.system_prompt]

        # 注入触发技能 (Tier 2)
        if triggered_skill_context:
            parts.append(triggered_skill_context)

        # 注入实时市场数据
        if stock_data_context:
            parts.append(
                "The following real-time market data has been retrieved by the system. "
                "Use these specific numbers in your analysis. "
                "Do NOT ask the user to look up this data themselves.\n\n"
                + stock_data_context
            )

        # 注入用户记忆上下文
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
            parts.append(f"<reference_knowledge>\nThe following are excerpts from your books and writings. Use ONLY if directly relevant to the user's current question — ignore if unrelated. These are NOT part of the current conversation.\n\n{knowledge_context}\n</reference_knowledge>")

        return "\n\n".join(parts)

    def _format_recent_dialogue(
        self, messages: list[Message], max_messages: int = 16, max_chars: int = 0
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
            if max_chars and len(content) > max_chars:
                content = content[:max_chars] + "..."

            if msg.role == MessageRole.USER:
                speaker = "用户"
            else:
                speaker = msg.name or "AI"

            lines.append(f"- {speaker}: {content}")

        if not lines:
            return ""

        return "最近对话记录（按时间顺序，优先引用其中的具体内容来回应）：\n" + "\n".join(lines)
