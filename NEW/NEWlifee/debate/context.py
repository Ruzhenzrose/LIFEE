"""
辩论上下文 - 参考 clawdbot 的 extraSystemPrompt 机制
"""
from dataclasses import dataclass
from typing import Optional

from .participant import ParticipantInfo


# 停止令牌 - 角色返回此令牌表示不想继续对话
REPLY_SKIP_TOKEN = "[[PASS]]"


@dataclass
class DebateContext:
    """辩论上下文 - 用于构建 Agent-to-Agent 的上下文提示"""

    current_participant: ParticipantInfo  # 当前发言者
    all_participants: list[ParticipantInfo]  # 所有参与者
    round_number: int  # 当前轮次
    speaking_order: int  # 当前发言顺序（1-based）
    total_speakers: int  # 总发言人数
    reply_to: Optional[ParticipantInfo] = None  # 正在回复谁（None=回复用户）

    def build_context_prompt(self) -> str:
        others = [
            p for p in self.all_participants
            if p.name != self.current_participant.name
        ]

        if not others:
            return self._build_single_participant_prompt()

        others_str = ", ".join([f"{p.emoji} {p.display_name}" for p in others])
        example_name = others[0].display_name

        base_context = f"""## Current Conversation

You are {self.current_participant.display_name}, taking part in a group discussion with the user and {others_str}. This is round {self.round_number}.

In the conversation history:
- The user's messages appear as `<user>...</user>`
- Your own previous messages appear as `<msg from="{self.current_participant.display_name}">...</msg>`"""

        for other in others:
            base_context += f'\n- {other.display_name}\'s messages appear as `<msg from="{other.display_name}">...</msg>`'

        base_context += """

Read the recent conversation carefully and engage with its actual content.

Always reply in the same language the user is using.

Note: the system will wrap your reply in message tags automatically — just speak directly, without adding any name, emoji, XML tag, or separator at the start."""

        if not self.reply_to:
            interaction_guide = f"""

### Your Turn

The user has just raised a question or topic. Respond from your own perspective.

**Guidelines**:
- Address the user's question directly
- Draw on your knowledge and worldview to offer insight and concrete guidance
- You may reference other participants (e.g. "As {example_name} said…") but it's not required
- Keep your voice and perspective distinct
- Be substantive but concise — leave room for others to speak
- You may include brief action descriptions in parentheses when they feel natural — e.g. (leaning forward), (a long pause)
- You must respond — staying silent is not an option
- End with at least one actionable suggestion the user can actually try
- If the user's situation is unclear, ask a clarifying question rather than guessing"""
        else:
            interaction_guide = """

### Your Turn

Others have already spoken. Now it's your turn to join the discussion.

**Guidelines**:
- Read the recent conversation and choose what you most want to engage with — the user's question, someone's argument, or the direction of the whole discussion
- You don't have to respond to the previous speaker specifically; follow your own judgment
- You may agree, build on, challenge, or open a new angle — your call
- Keep it concise: 2–3 paragraphs
- You may include brief action descriptions in parentheses when they feel natural — e.g. (leaning back), (a long pause)
- You must respond — staying silent is not an option"""

        return base_context + interaction_guide

    def _build_single_participant_prompt(self) -> str:
        return f"""## Current Conversation

You are {self.current_participant.display_name}, in a one-on-one conversation with the user. This is round {self.round_number}.

Always reply in the same language the user is using.

Note: the system will wrap your reply in message tags automatically — just speak directly, without adding any name, emoji, XML tag, or separator at the start.

### Your Turn

The user has just raised a question or topic. Respond from your own perspective.

**Guidelines**:
- Address the user's question directly
- Draw on your knowledge and worldview to offer insight and concrete guidance
- Keep your voice and perspective distinct
- You may include brief action descriptions in parentheses when they feel natural — e.g. (leaning forward), (a quiet smile)
- You must respond — staying silent is not an option
- End with at least one actionable suggestion the user can actually try
- If the user's situation is unclear, ask a clarifying question rather than guessing"""
