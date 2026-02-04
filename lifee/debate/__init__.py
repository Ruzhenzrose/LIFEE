"""
多智能体辩论系统

使用方式:
    from lifee.debate import Moderator, Participant, DebateContext

    # 创建参与者
    participants = [
        Participant(role_name, provider, role_manager, knowledge_manager)
        for role_name in role_manager.list_roles()
    ]

    # 创建主持者
    moderator = Moderator(participants, session)

    # 运行辩论（每个参与者会收到 DebateContext，知道其他参与者是谁）
    async for participant, chunk in moderator.run_round(user_input):
        print(f"{participant.info.emoji} {chunk}", end="")
"""

from .context import DebateContext, REPLY_SKIP_TOKEN
from .filter import StreamingFilter
from .moderator import Moderator, clean_response
from .participant import Participant, ParticipantInfo

__all__ = [
    "Moderator",
    "Participant",
    "ParticipantInfo",
    "DebateContext",
    "REPLY_SKIP_TOKEN",
    "clean_response",
    "StreamingFilter",
]
