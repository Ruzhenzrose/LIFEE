"""
辩论主持者 - 调度辩论流程
"""
import asyncio
import random
import re
import sys
from typing import AsyncIterator, Optional, Tuple

from lifee.providers.base import MediaItem, Message, RateLimitError, RetryableError
from lifee.sessions import Session

# 重试配置
MAX_RETRIES = 3  # 最大重试次数
RETRY_DELAY = 2.0  # 重试延迟（秒）
RATE_LIMIT_DELAY = 15.0  # 速率限制重试延迟（秒）
SPEAKER_DELAY = 5.0  # 角色之间的延迟（秒），OAuth token 需要足够长间隔避免速率限制
DEBUG_RESPONSE = False  # 调试响应生成（设为 True 可查看详细日志）

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

    def set_first(self, index: int) -> None:
        """覆盖第一个发言者（仅在首次 next() 前有效）"""
        self._index = index % self._count
        self._prev_index = None

    def reorder(self, sorted_participants: list) -> None:
        """按 RAG 相关度重排发言顺序（每轮用户输入后调用）"""
        self.participants = sorted_participants
        self._count = len(sorted_participants)
        self._index = 0
        self._prev_index = None


class Moderator:
    """辩论主持者 - 调度辩论流程"""

    def __init__(
        self,
        participants: list[Participant],
        session: Session,
        user_memory_context: Optional[str] = None,
        enable_moderator_check: bool = False,
        language: str = "",
    ):
        self.participants = participants
        self.session = session
        self.round_number = 0  # 轮次计数
        self.rotation = SpeakerRotation(participants, randomize_first=True)
        self.user_memory_context = user_memory_context  # 用户记忆上下文
        self.enable_moderator_check = enable_moderator_check  # 主持人预审开关
        self.language = language  # 用户偏好语言

    async def check_clarification(self, user_input: str) -> str | None:
        """主持人预审：判断用户输入是否需要补充信息。

        仅在第一轮、开关开启时触发。
        返回追问文本（需要补充时），或 None（信息已充分）。
        """
        if not self.enable_moderator_check:
            return None
        if self.round_number > 3:  # 前3轮可以追问，之后不再追问
            return None
        if not user_input or len(user_input.strip()) < 5:
            return None

        from lifee.providers.base import MessageRole

        provider = self.participants[0].provider
        names = "、".join(p.info.display_name for p in self.participants)

        prompt = f"""You are deciding whether to ask follow-up questions before {names} discuss the user's topic.

User said:
{user_input}

Rules:
- If the question is already specific enough (contains key context), output: PASS
- If key details are missing that would make the advice generic, ask 2-3 casual follow-up questions
- ONLY ask when truly needed. Simple greetings, clear questions, or specific scenarios → PASS

If follow-up is needed:
- Sound like a curious friend, NOT a survey or intake form
- Give 2-3 options per question so the user can quickly pick
- Max 3 questions
- Start with a brief, warm transition line
- Reply in the same language as the user

Example:
想更好地帮你分析，能先聊几个小问题吗？

1. 你目前大概处于什么阶段？
   A. 刚毕业/工作1-2年  B. 工作3-5年  C. 5年以上

2. 你最在意的是什么？
   A. 收入和稳定  B. 成长和学习  C. 自由和生活质量

If info is sufficient, just output: PASS"""

        try:
            response = await provider.chat(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                max_tokens=400,
                temperature=0.3,
            )
            result = response.content.strip()
            if result.upper().startswith("PASS"):
                return None
            return result
        except Exception:
            return None

    async def run(
        self,
        user_input: str,
        max_turns: int = 10,
        media: Optional[list] = None,
        mentioned_only: Optional[Participant] = None,
    ) -> AsyncIterator[Tuple[Participant, str, bool]]:
        """
        运行对话 - 统一的对话循环

        流程：
        1. 添加用户消息
        2. 第一个角色回复用户（reply_to=None）
        3. 后续角色回复上一个发言者（reply_to=上一个角色）
        4. 直到达到 max_turns 或某个角色返回 [[PASS]]

        Args:
            user_input: 用户输入
            max_turns: 最大发言轮次（默认 10）
            media: 用户附带的图片等多媒体

        Yields:
            (participant, chunk, is_skip) - 参与者、文本片段、是否跳过
        """
        # 增加轮次计数
        self.round_number += 1

        # 0. 上下文压缩检查（接近 token 上限时自动压缩）
        provider = self.participants[0].provider
        if await self.session.compact_if_needed(provider):
            print("[compact] Context compressed to save tokens")

        # 1. 添加用户消息到会话
        self.session.add_user_message(user_input, media=media)

        # 1.5 追问检查
        if self.enable_moderator_check:
            followup = await self.check_clarification(user_input)
            if followup:
                self.session.add_assistant_message(followup, name="LIFEE")
                # 用一个虚拟 participant 标识追问，personaId = "lifee-followup"
                class _FollowUpProxy:
                    info = ParticipantInfo(name="lifee-followup", display_name="LIFEE", emoji="💬")
                yield (_FollowUpProxy(), followup, False)
                return

        # 获取所有参与者信息（用于构建上下文）
        all_participants_info = [p.info for p in self.participants]
        num_participants = len(self.participants)

        # 2a. 多参与者时，根据 RAG 相关度重排发言顺序
        if num_participants > 1 and user_input:
            search_tasks = [p._search_knowledge(user_input) for p in self.participants]
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            scores = [
                max((r.score for r in res), default=0.0)
                if isinstance(res, list) else 0.0
                for res in all_results
            ]
            if max(scores) > 0:
                sorted_participants = [
                    p for _, p in sorted(zip(scores, self.participants), key=lambda x: x[0], reverse=True)
                ]
                self.rotation.reorder(sorted_participants)

        # 2. 循环让角色发言
        for turn in range(1, max_turns + 1):
            # 角色之间添加延迟，避免 API 速率限制（单参与者无需延迟）
            if turn > 1 and num_participants > 1:
                await asyncio.sleep(SPEAKER_DELAY)

            # 获取下一个发言者
            if mentioned_only:
                participant = mentioned_only
            else:
                participant = self.rotation.next()
            # 上一个发言者（第一个角色时为 None，表示回复用户）
            prev_participant = self.rotation.previous if turn > 1 and not mentioned_only else None

            # 构建辩论上下文
            debate_context = DebateContext(
                current_participant=participant.info,
                all_participants=all_participants_info,
                round_number=self.round_number,
                speaking_order=turn,
                total_speakers=num_participants,
                reply_to=prev_participant.info if prev_participant else None,
                language=self.language,
            )

            # 获取当前对话历史
            messages = self.session.get_messages()

            # 调试：显示发送给 API 的消息结构
            if DEBUG_RESPONSE:
                print(f"\n[DEBUG {participant.info.display_name}] 消息数={len(messages)}")
                for i, msg in enumerate(messages):
                    content_preview = msg.content[:50].replace('\n', '\\n') if len(msg.content) > 50 else msg.content.replace('\n', '\\n')
                    print(f"  [{i}] {msg.role.value} (name={msg.name}): {content_preview}...")

            # 带重试的响应生成（仅对瞬时错误重试，确定性错误直接放弃）
            final_response = ""
            yielded_anything = False
            last_error = None

            for retry in range(MAX_RETRIES + 1):
                full_response = ""
                stream_filter = StreamingFilter()
                chunk_count = 0
                hit_rate_limit = False

                try:
                    async for chunk in participant.respond(
                        messages=messages,
                        user_query=user_input,
                        debate_context=debate_context,
                        user_memory_context=self.user_memory_context,
                    ):
                        chunk_count += 1
                        full_response += chunk
                        filtered = stream_filter.process(chunk)

                        if not yielded_anything:
                            yield (participant, filtered, False)
                            yielded_anything = True
                        elif filtered:
                            yield (participant, filtered, False)
                    last_error = None
                except RateLimitError as e:
                    hit_rate_limit = True
                    last_error = e
                except RetryableError as e:
                    last_error = e
                except Exception as e:
                    # 非 RetryableError（如 400 BadRequest）→ 不重试，直接放弃
                    last_error = e
                    sys.stdout.write(f"\n  ⚠ {participant.info.display_name}: {e}\n")
                    sys.stdout.flush()
                    break

                # 刷新过滤器缓冲区
                remaining = stream_filter.flush()
                if remaining:
                    if not yielded_anything:
                        yield (participant, remaining, False)
                        yielded_anything = True
                    else:
                        yield (participant, remaining, False)

                if DEBUG_RESPONSE:
                    print(f"\n[DEBUG {participant.info.display_name}] turn={turn}, retry={retry}, chunks={chunk_count}, len={len(full_response)}, error={last_error}")

                if chunk_count > 0 and full_response.strip():
                    final_response = full_response
                    # 更新精确 token 计数（从 API usage 获取）
                    usage = getattr(participant.provider, '_last_stream_usage', None)
                    if usage and usage.get('input_tokens'):
                        self.session.update_token_count(usage['input_tokens'])
                    break

                # 瞬时错误或空响应 → 重试
                if retry < MAX_RETRIES:
                    delay = RATE_LIMIT_DELAY if hit_rate_limit else RETRY_DELAY
                    sys.stdout.write(f"\r  ⏳ 等待重试 {retry + 1}/{MAX_RETRIES}...")
                    sys.stdout.flush()
                    await asyncio.sleep(delay)
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    yielded_anything = False
                else:
                    if last_error:
                        sys.stdout.write(f"\n  ⚠ {participant.info.display_name}: {last_error}\n")
                    else:
                        sys.stdout.write(f"\n  ⚠ {participant.info.display_name} 返回空响应\n")
                    sys.stdout.flush()
                    final_response = ""

            # 检查是否是跳过令牌（角色主动结束辩论）
            if REPLY_SKIP_TOKEN in final_response:
                if not yielded_anything:
                    yield (participant, "", False)
                yield (participant, "", True)
                break

            # 检查是否为空响应（API 失败 / 限流耗尽重试）
            cleaned_response = clean_response(final_response)
            if not cleaned_response.strip():
                # 跳过本角色，继续让其他角色发言（不产生空气泡）
                continue

            # 确保至少 yield 一次（流式成功但未 yield 的极少数情况）
            if not yielded_anything:
                yield (participant, cleaned_response, False)

            # 添加到会话历史（带上角色名字）
            self.session.add_assistant_message(
                content=cleaned_response,
                name=participant.info.display_name,
            )

    def get_participants_info(self) -> list[ParticipantInfo]:
        """获取所有参与者信息"""
        return [p.info for p in self.participants]
