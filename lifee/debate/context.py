"""
辩论上下文 - 参考 clawdbot 的 extraSystemPrompt 机制
"""
from dataclasses import dataclass, field
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

    # ping-pong 模式专用字段
    is_pingpong: bool = False  # 是否在 ping-pong 模式
    pingpong_turn: int = 0  # ping-pong 当前轮次
    pingpong_max_turns: int = 5  # ping-pong 最大轮次
    reply_to: Optional[ParticipantInfo] = None  # 正在回复的参与者

    def build_context_prompt(self) -> str:
        """
        构建上下文提示

        类似 clawdbot 的 buildAgentToAgentMessageContext，
        告诉当前角色其他参与者是谁，以及当前的对话状态。
        """
        # 获取其他参与者
        others = [
            p for p in self.all_participants
            if p.name != self.current_participant.name
        ]

        if others:
            others_str = ", ".join([f"{p.emoji} {p.display_name}" for p in others])
            # 使用第一个其他参与者作为示例
            example_name = others[0].display_name
        else:
            others_str = "（无）"
            example_name = "其他参与者"

        # 基础上下文（用自然语言，避免 LLM 模仿格式）
        base_context = f"""## 当前对话场景

你现在是 {self.current_participant.display_name}，正在与用户和 {others_str} 进行一场讨论。这是第 {self.round_number} 轮对话。

在对话历史中：
- 用户说的话没有特殊标记
- 你之前说过的话会显示为 `<msg from="{self.current_participant.display_name}">...</msg>`"""

        # 说明其他人的消息格式
        for other in others:
            base_context += f'\n- {other.display_name} 说的话会显示为 `<msg from="{other.display_name}">...</msg>`'

        base_context += """

请注意：系统会自动给你的回复添加标记，所以你只需要直接说话，不要在开头加任何名字、emoji、XML 标签或分隔线。"""

        # ping-pong 模式的额外上下文
        if self.is_pingpong and self.reply_to:
            pingpong_context = f"""

### Ping-Pong 对话模式

你正在与 {self.reply_to.emoji} {self.reply_to.display_name} 进行深入对话。
这是第 {self.pingpong_turn}/{self.pingpong_max_turns} 轮自动对话。

**重要规则**：
- 直接回应 {self.reply_to.display_name} 的最后发言
- 可以提出反驳、补充、或新的角度
- 如果你觉得讨论已经充分，或没有更多要说的，请**只回复** `{REPLY_SKIP_TOKEN}`（不要说任何其他话）
- 保持简洁，每次回复控制在 2-3 段以内"""
            interaction_guide = f"""

### 互动指南

- 直接回应 {self.reply_to.display_name} 的观点
- 保持你自己的独特视角和思考方式
- 回应要有深度，但也要简洁"""
        else:
            pingpong_context = ""
            interaction_guide = f"""

### 互动指南

- 你可以直接回应其他参与者的观点，使用他们的名字（如"正如{example_name}所说..."）
- 你可以提出不同的视角，甚至反驳他们的观点
- 保持你自己的独特视角和思考方式
- 回应要有深度，但也要简洁，留给其他参与者发言空间"""

        return base_context + pingpong_context + interaction_guide
