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
    language: str = ""  # 用户偏好语言（空=跟用户语言走）

    def build_context_prompt(self) -> str:
        others = [
            p for p in self.all_participants
            if p.name != self.current_participant.name
        ]

        # 语言指令
        lang_line = f"Reply in {self.language}." if self.language else "Reply in the same language the user is using."

        # 消息格式说明
        format_lines = f"""- The user's messages appear as `<user>...</user>`
- Your messages appear as `<msg from="{self.current_participant.display_name}">...</msg>`"""
        for other in others:
            format_lines += f'\n- {other.display_name}\'s messages appear as `<msg from="{other.display_name}">...</msg>`'

        if not self.reply_to:
            # === 第一个发言者：直接回应用户 ===
            if others:
                others_str = ", ".join([f"{p.display_name}" for p in others])
                context = f"""## Current Conversation

You are {self.current_participant.display_name}. The user is asking for your perspective. After you speak, {others_str} will share theirs.

{format_lines}

{lang_line}

### Your Turn

The user just spoke. Share your perspective on what they said.

- Speak directly to the user, as yourself
- Draw from your own experience, knowledge, and worldview
- Be specific and concrete — give actionable insight
- If the user's situation is vague, weave 1-2 natural follow-up questions into your response
- Stay concise — say what matters, skip the filler
- You may use brief action descriptions like (pausing to think) when natural
- The system wraps your reply in message tags automatically — just speak directly"""
            else:
                context = f"""## Current Conversation

You are {self.current_participant.display_name}, in a one-on-one conversation with the user.

{format_lines}

{lang_line}

### Your Turn

The user just spoke. Share your perspective.

- Speak directly to the user, as yourself
- Draw from your own experience, knowledge, and worldview
- Be specific and concrete — give actionable insight
- If the user's situation is vague, weave 1-2 natural follow-up questions into your response
- Stay concise — say what matters, skip the filler
- The system wraps your reply in message tags automatically — just speak directly"""
        else:
            # === 后续发言者：回应讨论 ===
            context = f"""## Current Conversation

You are {self.current_participant.display_name}, joining an ongoing discussion. The user and other participants have already spoken — read the conversation history above.

{format_lines}

{lang_line}

### Your Turn

Others have spoken. Now add your voice.

- Engage with what was actually said — agree, build on it, or offer a different angle
- Speak from your own perspective and experience
- Be specific and concrete — give actionable insight
- Stay concise — say what matters, skip the filler
- You may use brief action descriptions like (leaning forward) when natural
- The system wraps your reply in message tags automatically — just speak directly"""

        return context
