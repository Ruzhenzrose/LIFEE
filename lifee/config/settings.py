"""配置管理模块"""
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量和 .env 文件加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Claude API
    anthropic_api_key: str = Field(default="", description="Anthropic API Key")
    claude_model: str = Field(
        default="claude-opus-4-5",
        description="Claude 模型名称",
    )

    def get_anthropic_api_key(self) -> Optional[str]:
        """
        获取 Anthropic API Key

        优先级:
        1. 环境变量 ANTHROPIC_API_KEY
        2. Claude Code OAuth 凭据
        """
        # 优先使用环境变量
        if self.anthropic_api_key:
            return self.anthropic_api_key

        # 尝试读取 Claude Code 凭据
        from lifee.providers.auth import get_api_key_from_credentials
        return get_api_key_from_credentials()

    # Gemini API (后续使用)
    google_api_key: str = Field(default="", description="Google API Key")
    gemini_model: str = Field(default="gemini-pro", description="Gemini 模型名称")

    # OpenAI Embedding (用于 RAG)
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding 模型名称",
    )

    # 应用配置
    debug: bool = Field(default=False, description="调试模式")
    data_dir: Path = Field(default=Path("data"), description="数据目录")

    @property
    def sessions_dir(self) -> Path:
        """会话存储目录"""
        return self.data_dir / "sessions"

    @property
    def memory_db_path(self) -> Path:
        """SQLite 数据库路径"""
        return self.data_dir / "memory.db"


# 全局配置实例
settings = Settings()
