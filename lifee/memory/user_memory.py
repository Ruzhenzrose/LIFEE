"""用户记忆管理（参考 clawd/USER.md 实现）

跨会话存储用户信息，使用 Markdown 文件格式。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from lifee.providers.base import LLMProvider, Message, MessageRole


# 存储目录
LIFEE_DIR = Path.home() / ".lifee"
MEMORY_DIR = LIFEE_DIR / "memory"

# 默认 USER.md 模板（5 类记忆，参考 MemPalace 思路）
DEFAULT_USER_TEMPLATE = """# USER.md - 关于你

## 事实 (Facts)
*稳定不变的：年龄、职业、城市、家庭、教育背景*

## 事件 (Events)
*正在发生或最近发生的：换工作、纠结的决定、近期经历*

## 发现 (Insights)
*用户表达的自我洞察："我意识到我害怕失败"*

## 偏好 (Preferences)
*沟通风格、回答深度、不喜欢的话题*

## 建议 (Advice)
*角色给过的、用户接受或拒绝的建议*

---
*这个文件记录了你在讨论中透露的信息，帮助角色更好地理解你。*
"""

# 5 个分类标识符（用于按需加载）
SECTIONS = ["事实", "事件", "发现", "偏好", "建议"]

# 提取用户信息的 Prompt（5 类分类）
EXTRACT_PROMPT = """You are updating a long-term memory profile based on a recent conversation.

Current USER.md:
{current_content}

Recent conversation (only user messages matter, character responses are noise):
{conversation}

5 categories (the headers in USER.md are in Chinese, but this instruction is in English):
- **Facts** (事实) — verifiable, stable facts the user EXPLICITLY stated about themselves (age, job, location, family, key experiences). NOT speculation.
- **Events** (事件) — concrete things currently happening in user's life that they mentioned (decisions being weighed, recent changes, ongoing situations). Replace items that are clearly resolved or no longer active.
- **Insights** (发现) — meta-level realizations the user articulated about themselves (e.g. "I realized I always avoid conflict"). Must be the USER's own words, not AI's interpretation.
- **Preferences** (偏好) — how the user wants to be talked to (style, depth, topics to avoid). Only when EXPLICITLY expressed.
- **Advice** (建议) — concrete actions the user committed to taking (not just nodded along to). Only record if the user explicitly said they would act on it.

DO NOT record:
- Temporary moods ("feeling tired today")
- Anything the AI characters said
- Anything you're guessing or interpreting — only what the user literally stated
- Information already in the file (deduplicate)

Quality bar:
- If unsure whether to add something, DON'T add it
- Better to keep the file unchanged than to add noise
- Each line should be a single fact, no padding
- Match the language the user used in their messages

Output:
- The full updated USER.md in markdown
- Preserve the 5 ## headers exactly
- Bullet points only, no prose

Return ONLY the updated markdown content, no explanation."""


class UserMemory:
    """用户记忆管理

    跨会话存储用户信息，使用 Markdown 文件格式：
    - USER.md: 用户档案（基本信息、偏好）
    - YYYY-MM-DD.md: 每日笔记（讨论话题、见解）
    """

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.user_file = MEMORY_DIR / "USER.md"
        self._ensure_user_file()
        self._last_extracted_msg_count = 0  # 上次提取时的消息数

    def _ensure_user_file(self):
        """确保 USER.md 存在"""
        if not self.user_file.exists():
            self.user_file.write_text(DEFAULT_USER_TEMPLATE, encoding="utf-8")

    def _get_daily_file(self) -> Path:
        """获取今天的笔记文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return MEMORY_DIR / f"{today}.md"

    def get_context(self) -> str:
        """获取记忆上下文（用于注入 prompt）

        Returns:
            USER.md 完整内容 + 今天的笔记
        """
        parts = []

        if self.user_file.exists():
            content = self.user_file.read_text(encoding="utf-8")
            if content.strip() != DEFAULT_USER_TEMPLATE.strip():
                parts.append(content)

        daily = self._get_daily_file()
        if daily.exists():
            parts.append(daily.read_text(encoding="utf-8"))

        return "\n\n".join(parts) if parts else ""

    def update_user_profile(self, field: str, value: str):
        """更新 USER.md 中的字段

        Args:
            field: 字段名（如 "名字"）
            value: 字段值
        """
        content = self.user_file.read_text(encoding="utf-8")

        # 尝试更新现有字段
        pattern = rf"(\*\*{field}:\*\*) .*"
        if re.search(pattern, content):
            content = re.sub(pattern, rf"\1 {value}", content)
        else:
            # 在基本信息部分添加新字段
            content = content.replace(
                "## 偏好", f"- **{field}:** {value}\n\n## 偏好"
            )

        self.user_file.write_text(content, encoding="utf-8")

    def add_to_section(self, section: str, content: str):
        """添加内容到 USER.md 的指定部分

        Args:
            section: 部分名称（如 "偏好"、"背景"）
            content: 要添加的内容
        """
        file_content = self.user_file.read_text(encoding="utf-8")

        # 找到该部分并添加内容
        pattern = rf"(## {section}\n\n)"
        if re.search(pattern, file_content):
            # 检查是否已存在相同内容
            if content in file_content:
                return
            file_content = re.sub(pattern, rf"\1- {content}\n", file_content)
            self.user_file.write_text(file_content, encoding="utf-8")

    def add_daily_note(self, section: str, content: str):
        """添加今日笔记

        Args:
            section: 部分名称（如 "讨论话题"、"见解"）
            content: 要添加的内容
        """
        daily = self._get_daily_file()

        if daily.exists():
            file_content = daily.read_text(encoding="utf-8")
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            file_content = f"# {today}\n\n"

        # 检查是否已有该部分
        section_header = f"## {section}\n"
        if section_header in file_content:
            # 在该部分添加内容
            if content not in file_content:
                file_content = file_content.replace(
                    section_header, f"{section_header}\n- {content}"
                )
        else:
            # 创建新部分
            file_content += f"\n{section_header}\n- {content}\n"

        daily.write_text(file_content, encoding="utf-8")

    async def auto_extract(
        self, messages: List[Message], provider: LLMProvider
    ) -> bool:
        """自动从对话中提取用户信息，重写整个 USER.md（后台运行）

        Args:
            messages: 对话历史
            provider: LLM 提供者

        Returns:
            是否更新了文件
        """
        if not messages:
            return False

        # 对话没有新消息，跳过
        if len(messages) <= self._last_extracted_msg_count:
            return False

        # 只分析上次提取之后新增的消息
        recent = messages[self._last_extracted_msg_count:]
        self._last_extracted_msg_count = len(messages)

        if not recent:
            return False

        # 构建对话文本（只取用户消息 + AI 消息前100字）
        conversation_parts = []
        for msg in recent:
            if msg.role == MessageRole.USER:
                conversation_parts.append(f"User: {msg.content}")
            else:
                name = msg.name or "AI"
                conversation_parts.append(f"{name}: {msg.content[:100]}")

        conversation = "\n".join(conversation_parts)

        # 读取当前 USER.md
        current_content = self.user_file.read_text(encoding="utf-8") if self.user_file.exists() else ""

        try:
            response = await provider.chat(
                messages=[
                    Message(
                        role=MessageRole.USER,
                        content=EXTRACT_PROMPT.format(
                            current_content=current_content,
                            conversation=conversation,
                        ),
                    )
                ],
                max_tokens=1000,
                temperature=0.2,
            )

            updated = response.content.strip()
            if not updated or updated == current_content.strip():
                return False

            # 直接覆写文件（替代追加逻辑）
            self.user_file.write_text(updated, encoding="utf-8")
            return True

        except Exception:
            # 静默失败，不影响主流程
            return False

    def _parse_json(self, content: str) -> Optional[dict]:
        """解析 LLM 返回的 JSON"""
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            # 尝试提取 JSON 部分
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None

    def clear(self):
        """清空所有记忆"""
        if self.user_file.exists():
            self.user_file.unlink()
        self._ensure_user_file()

        # 删除所有日记
        for f in MEMORY_DIR.glob("????-??-??.md"):
            f.unlink()
