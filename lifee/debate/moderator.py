"""
辩论主持者 - 调度辩论流程
"""
import asyncio
import random
import re
from typing import AsyncIterator, Optional, Tuple

from lifee.providers.base import Message
from lifee.sessions import Session

# 重试配置
MAX_RETRIES = 2  # 最大重试次数
RETRY_DELAY = 1.5  # 重试延迟（秒）

from .context import DebateContext, REPLY_SKIP_TOKEN
from .filter import StreamingFilter
from .participant import Participant, ParticipantInfo


def clean_response(text: str) -> str:
    """
    清理 LLM 响应中可能泄露的格式标记

    移除：
    - <msg from="..."> 开头/结尾
    - </msg> 标签
    - --- 分隔线
    """
    # 移除 <msg from="..."> 开头
    text = re.sub(r'^<msg from="[^"]*">\s*', '', text)
    # 移除 </msg> 结尾
    text = re.sub(r'\s*</msg>$', '', text)
    # 移除 <msg from="..."> 在任意位置（有时会在中间出现）
    text = re.sub(r'<msg from="[^"]*">', '', text)
    # 移除 </msg> 在任意位置
    text = re.sub(r'</msg>', '', text)
    # 移除开头的 ---
    text = re.sub(r'^---\s*\n?', '', text)
    # 移除结尾的 ---
    text = re.sub(r'\n?---\s*$', '', text)
    return text.strip()


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
        self._prev_index: Optional[int] = None  # 明确追踪上一个发言者

    def next(self) -> Participant:
        """获取下一个发言者，并移动指针"""
        # 保存当前位置作为"上一个"
        if self._prev_index is not None:
            # 已经开始了，移动到下一个
            self._prev_index = self._index
            self._index = (self._index + 1) % self._count
        else:
            # 第一次调用，不移动，只记录
            self._prev_index = self._index  # 第一次的 prev 就是自己（会在后续被覆盖）
        return self.participants[self._index]

    @property
    def current(self) -> Optional[Participant]:
        """当前发言者（如果还没开始则为 None）"""
        return self.participants[self._index] if self._prev_index is not None else None

    @property
    def previous(self) -> Optional[Participant]:
        """上一个发言者（真正的上一次 next() 返回的人）"""
        if self._prev_index is None:
            return None
        # 在第一次 next() 后，prev 就是上一轮的发言者
        # 计算真正的上一个：当前 index 的前一个位置
        prev = (self._index - 1) % self._count
        return self.participants[prev]

    def peek_next(self) -> Participant:
        """预览下一个发言者（不移动指针）"""
        if self._prev_index is None:
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

            # 带重试的响应生成
            final_response = ""
            yielded_anything = False  # 追踪是否 yield 过任何内容

            for retry in range(MAX_RETRIES + 1):
                full_response = ""
                stream_filter = StreamingFilter()
                chunk_count = 0

                async for chunk in participant.respond(
                    messages=messages,
                    user_query=user_input,
                    debate_context=debate_context,
                ):
                    chunk_count += 1
                    full_response += chunk
                    filtered = stream_filter.process(chunk)

                    # 第一次 yield 时确保 debate.py 能检测到参与者切换
                    if not yielded_anything:
                        yield (participant, filtered)
                        yielded_anything = True
                    elif filtered:
                        yield (participant, filtered)

                # 刷新过滤器缓冲区
                remaining = stream_filter.flush()
                if remaining:
                    if not yielded_anything:
                        yield (participant, remaining)
                        yielded_anything = True
                    else:
                        yield (participant, remaining)

                # 检查是否成功获取响应
                if chunk_count > 0:
                    final_response = full_response
                    break

                # 空响应，尝试重试
                if retry < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    final_response = ""

            # 确保至少 yield 一次（如果所有重试都失败）
            if not yielded_anything:
                yield (participant, "")

            # 添加到会话历史（带上角色名字，清理可能的格式泄露）
            self.session.add_assistant_message(
                content=clean_response(final_response),
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

            # 带重试的响应生成
            final_response = ""
            yielded_anything = False

            for retry in range(MAX_RETRIES + 1):
                full_response = ""
                stream_filter = StreamingFilter()
                chunk_count = 0

                async for chunk in current_participant.respond(
                    messages=messages,
                    user_query="",  # ping-pong 模式不需要用户查询
                    debate_context=debate_context,
                ):
                    chunk_count += 1
                    full_response += chunk
                    filtered = stream_filter.process(chunk)

                    # 第一次 yield 时确保 debate.py 能检测到参与者切换
                    if not yielded_anything:
                        yield (current_participant, filtered, False)
                        yielded_anything = True
                    elif filtered:
                        yield (current_participant, filtered, False)

                # 刷新过滤器缓冲区
                remaining = stream_filter.flush()
                if remaining:
                    if not yielded_anything:
                        yield (current_participant, remaining, False)
                        yielded_anything = True
                    else:
                        yield (current_participant, remaining, False)

                # 检查是否成功获取响应
                if chunk_count > 0:
                    final_response = full_response
                    break

                # 空响应，尝试重试
                if retry < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    final_response = ""

            # 确保至少 yield 一次（如果所有重试都失败）
            if not yielded_anything:
                yield (current_participant, "", False)

            # 检查是否是跳过令牌
            if REPLY_SKIP_TOKEN in final_response:
                yield (current_participant, "", True)
                break

            # 添加到会话历史（清理可能的格式泄露）
            self.session.add_assistant_message(
                content=clean_response(final_response),
                name=current_participant.info.display_name,
            )
