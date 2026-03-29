"""会话存储管理"""
import json
import time
from pathlib import Path
from typing import Dict, Optional

from .session import Session


class SessionStore:
    """
    会话存储管理器

    支持内存缓存和 JSON 文件持久化
    参考 clawdbot 的 45 秒 TTL 缓存策略
    """

    def __init__(self, storage_dir: Optional[Path] = None, cache_ttl: int = 45):
        """
        初始化会话存储

        Args:
            storage_dir: 持久化目录，None 表示仅使用内存
            cache_ttl: 缓存 TTL（秒）
        """
        self._storage_dir = storage_dir
        self._cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[Session, float]] = {}  # {session_id: (session, timestamp)}

        if storage_dir:
            storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Optional[Path]:
        """获取会话文件路径"""
        if self._storage_dir is None:
            return None
        return self._storage_dir / f"{session_id}.json"

    def _is_cache_valid(self, session_id: str) -> bool:
        """检查缓存是否有效"""
        if session_id not in self._cache:
            return False
        _, timestamp = self._cache[session_id]
        return (time.time() - timestamp) < self._cache_ttl

    def get(self, session_id: str) -> Optional[Session]:
        """
        获取会话

        Args:
            session_id: 会话 ID

        Returns:
            Session 或 None
        """
        # 检查缓存
        if self._is_cache_valid(session_id):
            return self._cache[session_id][0]

        # 尝试从文件加载
        path = self._get_session_path(session_id)
        if path and path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            session = Session.from_dict(data)
            self._cache[session_id] = (session, time.time())
            return session

        return None

    def save(self, session: Session):
        """
        保存会话

        Args:
            session: 要保存的会话
        """
        # 更新缓存
        self._cache[session.id] = (session, time.time())

        # 持久化到文件
        path = self._get_session_path(session.id)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def create(self, agent_id: Optional[str] = None) -> Session:
        """
        创建新会话

        Args:
            agent_id: 关联的 Agent ID

        Returns:
            新创建的 Session
        """
        session = Session(agent_id=agent_id)
        self.save(session)
        return session

    def delete(self, session_id: str):
        """
        删除会话

        Args:
            session_id: 会话 ID
        """
        # 从缓存移除
        self._cache.pop(session_id, None)

        # 删除文件
        path = self._get_session_path(session_id)
        if path and path.exists():
            path.unlink()

    def list_sessions(self) -> list[str]:
        """
        列出所有会话 ID

        Returns:
            会话 ID 列表
        """
        session_ids = set(self._cache.keys())

        if self._storage_dir and self._storage_dir.exists():
            for path in self._storage_dir.glob("*.json"):
                session_ids.add(path.stem)

        return list(session_ids)

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
