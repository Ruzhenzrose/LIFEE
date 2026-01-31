"""
辩论主持者 - 调度辩论流程
"""
import random
from typing import AsyncIterator, Optional, Tuple

from lifee.providers.base import Message
from lifee.sessions import Session

from .context import DebateContext, REPLY_SKIP_TOKEN
from .participant import Participant, ParticipantInfo


class SpeakerRotation:
    """发言顺序轮换器 - 自动管理谁下一个说话"""

    def __init__(self, participants: list[Participant], randomize_first: bool = True):
        """
        Args:
            participants: 参与者列表
            randomize_first: 是否随机选择第一个发言者
        """
        self.participants = participants
        self._count = len(participants)
        self._index = random.randrange(self._count) if randomize_first else 0
        self._started = False

    def next(self) -> Participant:
        """获取下一个发言者，并移动指针"""
        if self._started:
            self._index = (self._index + 1) % self._count
        self._started = True
        return self.participants[self._index]

    @property
    def current(self) -> Optional[Participant]:
        """当前发言者（如果还没开始则为 None）"""
        return self.participants[self._index] if self._started else None

    @property
    def previous(self) -> Optional[Participant]:
        """上一个发言者"""
        if not self._started:
            return None
        prev = (self._index - 1) % self._count
        return self.participants[prev]

    def peek_next(self) -> Participant:
        """预览下一个发言者（不移动指针）"""
        if not self._started:
            return self.participants[self._index]
        next_idx = (self._index + 1) % self._count
        return self.participants[next_idx]


class Moderator:
    """辩论主持者 - 调度辩论流程"""

    def __init__(
        self,
        participants: list[Participant],
        session: Session,
    ):
        self.participants = participants
        self.session = session
        self.round_number = 0  # 轮次计数
        self.rotation = SpeakerRotation(participants, randomize_first=True)

    async def run_round(
        self,
        user_input: str,
    ) -> AsyncIterator[Tuple[Participant, str]]:
        """
        运行一轮辩论

        Args:
            user_input: 用户输入

        Yields:
            (participant, chunk) - 参与者和文本片段
        """
        # 增加轮次计数
        self.round_number += 1

        # 1. 添加用户消息到会话
        self.session.add_user_message(user_input)

        # 获取所有参与者信息（用于构建上下文）
        all_participants_info = [p.info for p in self.participants]
        num_participants = len(self.participants)

        # 2. 依次让每个参与者发言（使用 rotation 管理顺序）
        for i in range(num_participants):
            participant = self.rotation.next()

            # 构建辩论上下文（类似 clawdbot 的 extraSystemPrompt）
            debate_context = DebateContext(
                current_participant=participant.info,
                all_participants=all_participants_info,
                round_number=self.round_number,
                speaking_order=i + 1,
                total_speakers=num_participants,
            )

            # 获取当前对话历史
            messages = self.session.get_messages()

            # 生成回应（传入辩论上下文）
            full_response = ""
            async for chunk in participant.respond(
                messages=messages,
                user_query=user_input,
                debate_context=debate_context,
            ):
                yield (participant, chunk)
                full_response += chunk

            # 添加到会话历史（带上角色名字）
            self.session.add_assistant_message(
                content=full_response,
                name=participant.info.display_name,
            )

    def get_participants_info(self) -> list[ParticipantInfo]:
        """获取所有参与者信息"""
        return [p.info for p in self.participants]

    async def run_pingpong(
        self,
        max_turns: int = 5,
    ) -> AsyncIterator[Tuple[Participant, str, bool]]:
        """
        运行 ping-pong 对话 - 角色之间自动持续对话

        在 run_round 之后调用，让角色之间继续交流。
        自动从最后发言者的下一个开始（由 rotation 管理）。

        Args:
            max_turns: 最大轮次（默认 5）

        Yields:
            (participant, chunk, is_skip) - 参与者、文本片段、是否跳过
        """
        if len(self.participants) < 2:
            return  # 至少需要 2 个参与者

        all_participants_info = [p.info for p in self.participants]
        num_participants = len(self.participants)

        for turn in range(1, max_turns + 1):
            # 获取下一个发言者（rotation 自动管理顺序）
            current_participant = self.rotation.next()
            # 上一个发言者（被回复的人）
            prev_participant = self.rotation.previous

            # 构建 ping-pong 上下文
            debate_context = DebateContext(
                current_participant=current_participant.info,
                all_participants=all_participants_info,
                round_number=self.round_number,
                speaking_order=turn,
                total_speakers=num_participants,
                is_pingpong=True,
                pingpong_turn=turn,
                pingpong_max_turns=max_turns,
                reply_to=prev_participant.info if prev_participant else None,
            )

            # 获取对话历史
            messages = self.session.get_messages()

            # 生成回应
            full_response = ""
            async for chunk in current_participant.respond(
                messages=messages,
                user_query="",  # ping-pong 模式不需要用户查询
                debate_context=debate_context,
            ):
                full_response += chunk
                yield (current_participant, chunk, False)

            # 检查是否是跳过令牌
            if REPLY_SKIP_TOKEN in full_response:
                yield (current_participant, "", True)
                break

            # 添加到会话历史
            self.session.add_assistant_message(
                content=full_response,
                name=current_participant.info.display_name,
            )
