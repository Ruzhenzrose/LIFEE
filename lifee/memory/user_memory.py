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

# 默认 USER.md 模板
DEFAULT_USER_TEMPLATE = """# USER.md - 关于你

- **名字:** (待了解)
- **称呼:** (待了解)

## 偏好

*(在对话中逐渐了解...)*

## 背景

*(在对话中逐渐了解...)*

---
*这个文件记录了你在讨论中透露的信息，帮助角色更好地理解你。*
"""

# 提取用户信息的 Prompt（重写整个文件，避免重复积累）
EXTRACT_PROMPT = """You are updating a user profile file based on a recent conversation.

Current USER.md content:
{current_content}

Recent conversation:
{conversation}

The file has three key sections:
- **How** — communication style preferences
- **What now** — what the user is currently focused on or thinking about (replace with latest)
- **What not** — topics or behaviors to avoid
- **背景参考** — stable background info (interests, personality)

Task: Produce an updated USER.md that:
1. Updates "What now" to reflect what the user seemed focused on in this conversation
2. Adds to "What not" if the user showed discomfort with something
3. Adds to "背景参考" only if genuinely new stable info was revealed
4. Does NOT repeat items already covered; deduplicates similar items
5. Keeps the file concise — prefer updating existing lines over adding new ones
6. Preserves the structure and Chinese language
7. If nothing new was learned, return the original content unchanged

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
            USER.md 内容 + 今天的笔记（如果存在）
        """
        parts = []

        # 读取 USER.md
        if self.user_file.exists():
            content = self.user_file.read_text(encoding="utf-8")
            # 检查是否有实际用户信息（不只是默认模板）
            # 简单检查：如果内容与默认模板不同，说明有更新
            if content.strip() != DEFAULT_USER_TEMPLATE.strip():
                parts.append(content)

        # 读取今天的笔记
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

        # 只分析最近的消息
        recent = messages[-6:]

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
