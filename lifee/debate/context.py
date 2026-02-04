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
            example_name = others[0].display_name
        else:
            others_str = "（无）"
            example_name = "其他参与者"

        # 基础上下文（用自然语言，避免 LLM 模仿格式）
        base_context = f"""## 当前对话场景

你现在是 {self.current_participant.display_name}，正在与用户和 {others_str} 进行一场讨论。这是第 {self.round_number} 轮对话。

在对话历史中：
- 用户说的话会显示为 `<user>...</user>`
- 你之前说过的话会显示为 `<msg from="{self.current_participant.display_name}">...</msg>`"""

        # 说明其他人的消息格式
        for other in others:
            base_context += f'\n- {other.display_name} 说的话会显示为 `<msg from="{other.display_name}">...</msg>`'

        base_context += """

请注意：系统会自动给你的回复添加标记，所以你只需要直接说话，不要在开头加任何名字、emoji、XML 标签或分隔线。"""

        # 根据 reply_to 构建不同的互动指南
        if self.reply_to:
            # 回复另一个角色
            interaction_guide = f"""

### 当前任务

你正在回应 {self.reply_to.emoji} {self.reply_to.display_name} 的发言。

**规则**：
- 直接回应 {self.reply_to.display_name} 的观点，从你独特的视角补充或对话
- 可以表示认同、提出不同角度、或深入探讨某个点
- 保持简洁，每次回复控制在 2-3 段以内
- 保持你自己的独特视角和思考方式
- 你必须回应，不能保持沉默"""
        else:
            # 回复用户（第一个发言）
            interaction_guide = f"""

### 当前任务

用户刚才提出了一个问题或话题，请以你的视角回应。

**规则**：
- 直接回应用户的问题
- 你可以提及其他参与者（如"正如{example_name}所说..."），但这不是必须的
- 保持你自己的独特视角和思考方式
- 回应要有深度，但也要简洁，留给其他参与者发言空间"""

        return base_context + interaction_guide
