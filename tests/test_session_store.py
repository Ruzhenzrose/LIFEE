"""测试会话自动存储"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lifee.sessions.debate_store import DebateSessionStore, ChatSessionStore
from lifee.sessions import Session
from lifee.providers.base import MessageRole


class TestDebateSessionStore:
    """测试 DebateSessionStore"""

    @pytest.fixture
    def store(self, tmp_path):
        """使用临时目录创建 store"""
        current_path = tmp_path / "sessions" / "current.json"
        history_dir = tmp_path / "sessions" / "history"
        return DebateSessionStore(current_path=current_path, history_dir=history_dir)

    @pytest.fixture
    def paths(self, store):
        """获取 store 的路径"""
        return {
            "current_session": store._current_path,
            "history_dir": store._history_dir,
        }

    def test_init_creates_directories(self, store, paths):
        """初始化时创建目录"""
        assert paths["current_session"].parent.exists()
        assert paths["history_dir"].exists()

    def test_save_and_load(self, store):
        """保存和加载会话"""
        # 创建会话
        session = Session()
        session.add_user_message("你好")
        session.add_assistant_message("你好！", name="克里希那穆提")

        # 保存
        store.save(session, ["克里希那穆提", "拉康"])

        # 加载
        loaded = store.load()
        assert loaded is not None
        assert loaded["participants"] == ["克里希那穆提", "拉康"]
        assert len(loaded["history"]) == 2

    def test_load_nonexistent(self, store):
        """加载不存在的会话"""
        loaded = store.load()
        assert loaded is None

    def test_load_expired_session(self, store, paths):
        """加载过期会话返回 None 并归档"""
        # 创建过期会话
        data = {
            "session_id": "test",
            "updated_at": (datetime.now() - timedelta(hours=25)).isoformat(),
            "participants": ["A"],
            "history": [],
        }
        paths["current_session"].write_text(json.dumps(data), encoding="utf-8")

        # 加载应返回 None
        loaded = store.load()
        assert loaded is None

        # 应该被归档
        assert not paths["current_session"].exists()
        assert len(list(paths["history_dir"].glob("*.json"))) == 1

    def test_restore_session(self, store):
        """恢复 Session 对象"""
        data = {
            "session_id": "test-id",
            "updated_at": datetime.now().isoformat(),
            "participants": ["A", "B"],
            "history": [
                {"role": "user", "content": "问题"},
                {"role": "assistant", "content": "回答", "name": "A"},
            ],
        }

        session = store.restore_session(data)
        assert session.id == "test-id"
        assert len(session.history) == 2
        assert session.history[0].role == MessageRole.USER
        assert session.history[1].name == "A"

    def test_archive(self, store, paths):
        """归档会话"""
        # 创建会话文件
        paths["current_session"].write_text('{"test": 1}', encoding="utf-8")

        # 归档
        store.archive()

        # 验证
        assert not paths["current_session"].exists()
        archived = list(paths["history_dir"].glob("*.json"))
        assert len(archived) == 1

    def test_clear(self, store, paths):
        """清除会话"""
        # 创建会话文件
        paths["current_session"].write_text('{"test": 1}', encoding="utf-8")

        # 清除
        store.clear()

        # 验证
        assert not paths["current_session"].exists()
        assert len(list(paths["history_dir"].glob("*.json"))) == 0

    def test_get_time_ago(self, store):
        """测试时间描述"""
        # 刚刚
        data = {"updated_at": datetime.now().isoformat()}
        assert store.get_time_ago(data) == "刚刚"

        # 5 分钟前
        data = {"updated_at": (datetime.now() - timedelta(minutes=5)).isoformat()}
        assert "5分钟前" in store.get_time_ago(data)

        # 2 小时前
        data = {"updated_at": (datetime.now() - timedelta(hours=2)).isoformat()}
        assert "2小时前" in store.get_time_ago(data)

    def test_list_history_empty(self, store):
        """列出空历史"""
        sessions = store.list_history()
        assert sessions == []

    def test_list_history(self, store, paths):
        """列出历史会话"""
        # 创建几个历史会话
        for i in range(3):
            data = {
                "session_id": f"test-{i}",
                "updated_at": datetime.now().isoformat(),
                "participants": ["A", "B"],
                "history": [{"role": "user", "content": f"msg-{i}"}],
            }
            filename = f"2026020{i}_120000.json"
            (paths["history_dir"] / filename).write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )

        sessions = store.list_history()
        assert len(sessions) == 3
        # 应该按时间倒序
        assert sessions[0]["filename"] == "20260202_120000.json"
        assert sessions[0]["participants"] == ["A", "B"]
        assert sessions[0]["msg_count"] == 1

    def test_load_history(self, store, paths):
        """加载历史会话"""
        # 创建历史会话
        data = {
            "session_id": "test-history",
            "updated_at": datetime.now().isoformat(),
            "participants": ["C", "D"],
            "history": [{"role": "user", "content": "hello"}],
        }
        filename = "20260202_120000.json"
        (paths["history_dir"] / filename).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        # 加载
        loaded = store.load_history(filename)
        assert loaded is not None
        assert loaded["session_id"] == "test-history"
        assert loaded["participants"] == ["C", "D"]

    def test_load_history_nonexistent(self, store):
        """加载不存在的历史会话"""
        loaded = store.load_history("nonexistent.json")
        assert loaded is None


class TestChatSessionStore:
    """测试 ChatSessionStore 使用独立路径"""

    def test_chat_store_uses_separate_paths(self):
        """ChatSessionStore 应使用独立的存储路径"""
        from lifee.sessions.debate_store import (
            CHAT_CURRENT_SESSION, CHAT_HISTORY_DIR,
            DEBATE_CURRENT_SESSION, DEBATE_HISTORY_DIR,
        )
        # 对话和辩论的路径应该不同
        assert CHAT_CURRENT_SESSION != DEBATE_CURRENT_SESSION
        assert CHAT_HISTORY_DIR != DEBATE_HISTORY_DIR

    def test_chat_store_save_and_load(self, tmp_path):
        """ChatSessionStore 基本保存加载"""
        current_path = tmp_path / "chat" / "current.json"
        history_dir = tmp_path / "chat" / "history"
        # 直接用父类构造器传参来测试
        store = DebateSessionStore(current_path=current_path, history_dir=history_dir)

        session = Session()
        session.add_user_message("你好")
        session.add_assistant_message("你好！")

        store.save(session, ["lacan"])

        loaded = store.load()
        assert loaded is not None
        assert loaded["participants"] == ["lacan"]
        assert len(loaded["history"]) == 2
