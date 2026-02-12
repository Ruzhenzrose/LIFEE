"""会话自动存储（参考 clawdbot 实现）"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .session import Session
from lifee.providers.base import Message, MessageRole


# 默认存储目录
LIFEE_DIR = Path.home() / ".lifee"

# 统一会话路径
SESSIONS_DIR = LIFEE_DIR / "sessions"
CURRENT_SESSION = SESSIONS_DIR / "current.json"
HISTORY_DIR = SESSIONS_DIR / "history"

# 旧的对话模式路径（用于迁移）
_OLD_CHAT_SESSIONS_DIR = LIFEE_DIR / "chat_sessions"

# 向后兼容别名
DEBATE_SESSIONS_DIR = SESSIONS_DIR
DEBATE_CURRENT_SESSION = CURRENT_SESSION
DEBATE_HISTORY_DIR = HISTORY_DIR

# 会话过期时间（小时）
SESSION_EXPIRE_HOURS = 24


class DebateSessionStore:
    """会话自动存储

    参考 clawdbot 的 sessions.json 结构，实现：
    - 自动保存当前会话到 current.json
    - 启动时自动检查并恢复
    - 过期会话自动归档到 history/
    """

    def __init__(self, current_path=None, history_dir=None):
        self._current_path = current_path or CURRENT_SESSION
        self._history_dir = history_dir or HISTORY_DIR
        self._current_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_old_chat_sessions()

    def save(self, session: Session, participants: list[str]):
        """自动保存当前会话

        Args:
            session: 会话对象
            participants: 参与者名称列表
        """
        data = {
            "session_id": session.id,
            "updated_at": datetime.now().isoformat(),
            "participants": participants,
            "history": [msg.to_dict() for msg in session.history],
        }
        self._current_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> Optional[dict]:
        """加载当前会话

        Returns:
            会话数据，如果不存在或已过期则返回 None
        """
        if not self._current_path.exists():
            return None

        try:
            data = json.loads(self._current_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

        # 检查是否过期
        try:
            updated = datetime.fromisoformat(data["updated_at"])
            if datetime.now() - updated > timedelta(hours=SESSION_EXPIRE_HOURS):
                self.archive()
                return None
        except (KeyError, ValueError):
            return None

        return data

    def restore_session(self, data: dict) -> Session:
        """从保存的数据恢复 Session 对象

        Args:
            data: load() 返回的数据

        Returns:
            恢复的 Session 对象
        """
        history = [
            Message(
                role=MessageRole(msg["role"]),
                content=msg["content"],
                name=msg.get("name"),
            )
            for msg in data.get("history", [])
        ]

        session = Session(id=data.get("session_id"))
        session.history = history
        return session

    def archive(self):
        """归档当前会话到历史目录"""
        if self._current_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = self._history_dir / f"{timestamp}.json"
            self._current_path.rename(dest)

    def clear(self):
        """清除当前会话（不归档）"""
        if self._current_path.exists():
            self._current_path.unlink()

    def get_time_ago(self, data: dict) -> str:
        """获取上次更新的时间描述

        Args:
            data: load() 返回的数据

        Returns:
            如 "2小时前"、"刚刚" 等
        """
        try:
            updated = datetime.fromisoformat(data["updated_at"])
            delta = datetime.now() - updated

            if delta.total_seconds() < 60:
                return "刚刚"
            elif delta.total_seconds() < 3600:
                return f"{int(delta.total_seconds() / 60)}分钟前"
            elif delta.total_seconds() < 86400:
                return f"{int(delta.total_seconds() / 3600)}小时前"
            else:
                return f"{int(delta.days)}天前"
        except (KeyError, ValueError):
            return "未知"

    def list_history(self, limit: int = 10) -> list[dict]:
        """列出历史会话

        Args:
            limit: 最多返回的会话数量

        Returns:
            历史会话列表，每个元素包含 filename, updated_at, participants, msg_count
        """
        sessions = []
        # 按文件名倒序排列（最新的在前）
        for f in sorted(self._history_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "filename": f.name,
                    "updated_at": data.get("updated_at", ""),
                    "participants": data.get("participants", []),
                    "msg_count": len(data.get("history", [])),
                })
            except (json.JSONDecodeError, IOError):
                pass
        return sessions

    def load_history(self, filename: str) -> Optional[dict]:
        """加载指定的历史会话

        Args:
            filename: 历史会话文件名（如 "20260202_120000.json"）

        Returns:
            会话数据，如果不存在则返回 None
        """
        path = self._history_dir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None


    def _migrate_old_chat_sessions(self):
        """一次性迁移旧的 chat_sessions 目录到统一路径"""
        if not _OLD_CHAT_SESSIONS_DIR.exists():
            return
        try:
            # 迁移历史文件
            old_history = _OLD_CHAT_SESSIONS_DIR / "history"
            if old_history.exists():
                for f in old_history.glob("*.json"):
                    dest = self._history_dir / f"chat_{f.name}"
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
            # 迁移当前会话（归档）
            old_current = _OLD_CHAT_SESSIONS_DIR / "current.json"
            if old_current.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = self._history_dir / f"chat_{timestamp}.json"
                shutil.move(str(old_current), str(dest))
            # 清理空目录
            if old_history.exists():
                old_history.rmdir()
            _OLD_CHAT_SESSIONS_DIR.rmdir()
        except OSError:
            pass  # 目录非空或权限问题，跳过


# 向后兼容别名
ChatSessionStore = DebateSessionStore
