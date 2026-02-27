"""
建议回复生成器 - 根据讨论内容生成用户可能的回复建议
"""
import json
import re
from typing import List

from lifee.providers.base import LLMProvider, Message


SUGGESTION_SYSTEM_PROMPT = """You are a conversation suggestion generator. Based on the current discussion context, generate 3 possible reply suggestions for the user.

Requirements:
1. Suggestions should be diverse:
   - One that digs deeper or asks for clarification
   - One that expresses the user's own viewpoint
   - One that shifts to a new topic or angle
2. Each suggestion should be brief (under 30 words)
3. Natural tone, like a real person, first person
4. IMPORTANT: Match the language of the conversation. If the conversation is in Chinese, suggest in Chinese. If in English, suggest in English.

Output format (strictly follow):
- Output only a JSON array: ["suggestion1", "suggestion2", "suggestion3"]
- No other text, explanations, or prefixes
- Start with [ and end with ]"""


class SuggestionGenerator:
    """生成用户回复建议"""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def generate(
        self,
        messages: List[Message],
        num_suggestions: int = 3,
    ) -> List[str]:
        """
        根据对话历史生成回复建议

        Args:
            messages: 对话历史
            num_suggestions: 建议数量

        Returns:
            建议列表，失败时返回空列表
        """
        try:
            # 将对话历史转换为摘要文本，作为单个 user 消息发送
            # 这样可以避免消息格式不符合 API 要求的问题
            context = self._format_context(messages)
            if not context:
                return []

            from lifee.providers.base import MessageRole
            request_messages = [
                Message(
                    role=MessageRole.USER,
                    content=f"Here is the current discussion:\n\n{context}\n\nGenerate 3 reply suggestions for the user. Match the language used in the conversation.",
                )
            ]

            response = await self.provider.chat(
                messages=request_messages,
                system=SUGGESTION_SYSTEM_PROMPT,
                temperature=0.8,
            )

            # 解析 JSON 响应
            suggestions = self._parse_suggestions(response.content)
            return suggestions[:num_suggestions]

        except Exception:
            # 任何错误都降级到空列表
            return []

    def _find_json_array(self, content: str) -> str | None:
        """找到第一个完整的 JSON 数组（正确处理字符串内的括号）"""
        start = content.find('[')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False

        for i, c in enumerate(content[start:], start):
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return content[start:i+1]

        return None

    def _format_context(self, messages: List[Message], max_messages: int = 6) -> str:
        """将消息列表格式化为上下文文本"""
        if not messages:
            return ""

        # 只取最近的几条消息
        recent = messages[-max_messages:]
        lines = []
        for msg in recent:
            if msg.role.value == "user":
                speaker = "User"
            else:
                speaker = "Assistant"
            lines.append(f"{speaker}: {msg.content[:200]}")  # 限制长度

        return "\n".join(lines)

    def _parse_suggestions(self, content: str) -> List[str]:
        """解析 LLM 返回的建议"""
        if not content:
            return []

        content = content.strip()

        # 尝试直接解析 JSON
        try:
            suggestions = json.loads(content)
            if isinstance(suggestions, list):
                return [str(s).strip() for s in suggestions if s]
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 数组部分 - 使用括号匹配而非正则
        json_str = self._find_json_array(content)
        if json_str:
            try:
                suggestions = json.loads(json_str)
                if isinstance(suggestions, list):
                    return [str(s).strip() for s in suggestions if s]
            except json.JSONDecodeError:
                pass

        # 尝试从 markdown 代码块中提取
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if code_match:
            try:
                suggestions = json.loads(code_match.group(1).strip())
                if isinstance(suggestions, list):
                    return [str(s).strip() for s in suggestions if s]
            except json.JSONDecodeError:
                pass

        # 最后尝试：按行分割，提取看起来像建议的内容
        lines = content.split('\n')
        suggestions = []
        for line in lines:
            line = line.strip()
            # 去掉常见的列表前缀
            line = re.sub(r'^[\d\.\-\*\•]+\s*', '', line)
            line = re.sub(r'^["「『]|["」』]$', '', line)  # 去掉引号
            if line and len(line) > 5 and len(line) < 100:
                suggestions.append(line)
        if suggestions:
            return suggestions[:3]

        return []
