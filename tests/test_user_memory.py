"""测试用户记忆"""
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from lifee.memory.user_memory import UserMemory, MEMORY_DIR, DEFAULT_USER_TEMPLATE
from lifee.providers.base import Message, MessageRole


class TestUserMemory:
    """测试 UserMemory"""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """使用临时目录"""
        memory_dir = tmp_path / "memory"
        with patch("lifee.memory.user_memory.MEMORY_DIR", memory_dir):
            yield memory_dir

    def test_init_creates_directory(self, temp_dir):
        """初始化时创建目录"""
        memory = UserMemory()
        assert temp_dir.exists()

    def test_init_creates_user_file(self, temp_dir):
        """初始化时创建 USER.md"""
        memory = UserMemory()
        user_file = temp_dir / "USER.md"
        assert user_file.exists()
        content = user_file.read_text(encoding="utf-8")
        assert "# USER.md" in content

    def test_get_context_empty(self, temp_dir):
        """空记忆返回空字符串"""
        memory = UserMemory()
        # 默认模板包含占位符，应该返回空
        ctx = memory.get_context()
        assert ctx == ""

    def test_get_context_with_data(self, temp_dir):
        """有数据时返回内容"""
        memory = UserMemory()

        # 更新用户信息
        memory.update_user_profile("名字", "小明")

        ctx = memory.get_context()
        assert "小明" in ctx

    def test_update_user_profile(self, temp_dir):
        """更新用户档案"""
        memory = UserMemory()

        memory.update_user_profile("名字", "小明")
        memory.update_user_profile("职业", "程序员")

        content = (temp_dir / "USER.md").read_text(encoding="utf-8")
        assert "**名字:** 小明" in content
        assert "**职业:** 程序员" in content

    def test_add_to_section(self, temp_dir):
        """添加内容到指定部分"""
        memory = UserMemory()

        memory.add_to_section("偏好", "喜欢简洁的回答")
        memory.add_to_section("偏好", "喜欢技术讨论")

        content = (temp_dir / "USER.md").read_text(encoding="utf-8")
        assert "- 喜欢简洁的回答" in content
        assert "- 喜欢技术讨论" in content

    def test_add_to_section_no_duplicate(self, temp_dir):
        """不重复添加相同内容"""
        memory = UserMemory()

        memory.add_to_section("偏好", "喜欢简洁")
        memory.add_to_section("偏好", "喜欢简洁")

        content = (temp_dir / "USER.md").read_text(encoding="utf-8")
        assert content.count("喜欢简洁") == 1

    def test_add_daily_note(self, temp_dir):
        """添加每日笔记"""
        memory = UserMemory()

        memory.add_daily_note("讨论话题", "人工智能的未来")

        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = temp_dir / f"{today}.md"
        assert daily_file.exists()

        content = daily_file.read_text(encoding="utf-8")
        assert f"# {today}" in content
        assert "## 讨论话题" in content
        assert "- 人工智能的未来" in content

    def test_clear(self, temp_dir):
        """清空所有记忆"""
        memory = UserMemory()

        # 添加数据
        memory.update_user_profile("名字", "小明")
        memory.add_daily_note("话题", "测试")

        # 清空
        memory.clear()

        # 验证
        content = (temp_dir / "USER.md").read_text(encoding="utf-8")
        assert "(待了解)" in content  # 恢复默认模板

        today = datetime.now().strftime("%Y-%m-%d")
        assert not (temp_dir / f"{today}.md").exists()

    @pytest.mark.asyncio
    async def test_auto_extract(self, temp_dir):
        """自动提取用户信息"""
        memory = UserMemory()

        # Mock provider
        mock_provider = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = '{"profile": {"name": "小明"}, "topics": ["AI讨论"]}'
        mock_provider.chat.return_value = mock_response

        messages = [
            Message(role=MessageRole.USER, content="我叫小明，今天想聊聊AI"),
            Message(role=MessageRole.ASSISTANT, content="你好小明！", name="角色A"),
        ]

        result = await memory.auto_extract(messages, mock_provider)
        assert result is True

        # 验证提取的信息
        content = (temp_dir / "USER.md").read_text(encoding="utf-8")
        assert "小明" in content

    @pytest.mark.asyncio
    async def test_auto_extract_empty_messages(self, temp_dir):
        """空消息列表返回 False"""
        memory = UserMemory()
        mock_provider = AsyncMock()

        result = await memory.auto_extract([], mock_provider)
        assert result is False

    @pytest.mark.asyncio
    async def test_auto_extract_error_handling(self, temp_dir):
        """提取失败时静默处理"""
        memory = UserMemory()

        mock_provider = AsyncMock()
        mock_provider.chat.side_effect = Exception("API Error")

        messages = [Message(role=MessageRole.USER, content="测试")]

        # 不应抛出异常
        result = await memory.auto_extract(messages, mock_provider)
        assert result is False
