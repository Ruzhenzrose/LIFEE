"""命令行工具 — 让 Claude Code 通过 Bash 调用 LIFEE 角色

每次调用必须指定 --session 名称，用于隔离不同场景的对话历史。
Session 文件存储在 ~/.lifee/sessions/ask/<name>.json
"""

import asyncio
import json
import sys
from pathlib import Path

# 确保 lifee 包可导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ask 专用 session 目录（与 LIFEE CLI 的 session 隔离）
ASK_SESSIONS_DIR = Path.home() / ".lifee" / "sessions" / "ask"


def _load_ask_session(name: str):
    """加载指定名称的 ask session"""
    from lifee.sessions import Session
    from lifee.providers.base import Message

    ASK_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = ASK_SESSIONS_DIR / f"{name}.json"

    if session_file.exists():
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            session = Session(id=data.get("session_id"))
            session.history = [Message.from_dict(m) for m in data.get("history", [])]
            participants = data.get("participants", [])
            return session, participants, session_file
        except (json.JSONDecodeError, IOError):
            pass

    return Session(), [], session_file


def _save_ask_session(session, participants, session_file):
    """保存 ask session"""
    from datetime import datetime

    data = {
        "session_id": session.id,
        "updated_at": datetime.now().isoformat(),
        "participants": participants,
        "history": [msg.to_dict() for msg in session.history],
    }
    session_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def ask(role: str, question: str, session_name: str):
    """问单个角色"""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    import os
    from lifee.cli.app import create_provider
    from lifee.roles import RoleManager
    from lifee.debate.participant import Participant
    from lifee.debate.moderator import Moderator

    rm = RoleManager()
    provider = create_provider()
    available = rm.list_roles()

    matched = next((a for a in available if a.lower() == role.lower()), None)
    if not matched:
        print(f"角色 '{role}' 不存在。可用: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    # 加载指定 session
    session, participants_names, session_file = _load_ask_session(session_name)

    # 创建参与者
    google_key = os.getenv("GOOGLE_API_KEY")
    km = await rm.get_knowledge_manager(matched, google_api_key=google_key) if google_key else None
    participant = Participant(matched, provider, rm, knowledge_manager=km)

    display_name = participant.info.display_name
    if display_name not in participants_names:
        participants_names.append(display_name)

    # 运行
    moderator = Moderator([participant], session)
    async for p, chunk, is_skip in moderator.run(question, max_turns=1):
        if not is_skip and chunk:
            sys.stdout.write(chunk)
            sys.stdout.flush()
    print()

    # 保存
    _save_ask_session(session, participants_names, session_file)


async def consult(roles: list[str], question: str, session_name: str):
    """多角色讨论"""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    import os
    from lifee.cli.app import create_provider
    from lifee.roles import RoleManager
    from lifee.debate.participant import Participant
    from lifee.debate.moderator import Moderator
    from lifee.debate import moderator as mod_module

    rm = RoleManager()
    provider = create_provider()
    available = rm.list_roles()

    valid_roles = []
    for r in roles:
        matched = next((a for a in available if a.lower() == r.lower()), None)
        if matched:
            valid_roles.append(matched)
    if not valid_roles:
        print(f"没有有效角色。可用: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    # 加载指定 session
    session, participants_names, session_file = _load_ask_session(session_name)

    # 创建参与者
    participants = []
    for role_name in valid_roles:
        google_key = os.getenv("GOOGLE_API_KEY")
        km = await rm.get_knowledge_manager(role_name, google_api_key=google_key) if google_key else None
        p = Participant(role_name, provider, rm, knowledge_manager=km)
        participants.append(p)
        if p.info.display_name not in participants_names:
            participants_names.append(p.info.display_name)

    # 去掉角色间延迟
    original_delay = mod_module.SPEAKER_DELAY
    mod_module.SPEAKER_DELAY = 0.0

    try:
        moderator = Moderator(participants, session)
        current_name = ""
        async for participant, chunk, is_skip in moderator.run(question, max_turns=len(participants)):
            if participant is None:
                continue  # moderator 的状态信号（kb_search / picked:...）CLI 忽略
            if is_skip:
                continue
            if participant.info.display_name != current_name:
                if current_name:
                    print("\n")
                current_name = participant.info.display_name
                sys.stdout.write(f"**{current_name}:**\n")
            sys.stdout.write(chunk)
            sys.stdout.flush()
        print()
    finally:
        mod_module.SPEAKER_DELAY = original_delay

    # 保存
    _save_ask_session(session, participants_names, session_file)


def list_sessions():
    """列出所有 ask sessions"""
    ASK_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for f in sorted(ASK_SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            n = len(data.get("history", []))
            p = ", ".join(data.get("participants", []))
            updated = data.get("updated_at", "")[:16].replace("T", " ")
            sessions.append(f"{f.stem} | {p} | {n} msgs | {updated}")
        except (json.JSONDecodeError, IOError):
            continue
    if sessions:
        print("\n".join(sessions))
    else:
        print("No sessions found.")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--list-sessions":
        list_sessions()
        return

    import argparse

    parser = argparse.ArgumentParser(description="LIFEE 角色咨询")
    parser.add_argument("--session", "-s", required=True, help="Session 名称（隔离不同场景的对话）")
    parser.add_argument("--consult", "-c", action="store_true", help="多角色讨论模式")
    parser.add_argument("--list-sessions", action="store_true", help="列出所有 sessions")
    parser.add_argument("role", help="角色名（多角色用逗号分隔）")
    parser.add_argument("question", help="问题")

    args = parser.parse_args()

    if args.consult or "," in args.role:
        roles = args.role.split(",")
        asyncio.run(consult(roles, args.question, args.session))
    else:
        asyncio.run(ask(args.role, args.question, args.session))


if __name__ == "__main__":
    main()
