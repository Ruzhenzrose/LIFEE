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

    # LLM Provider 选择
    llm_provider: str = Field(
        default="claude",
        description="LLM Provider: claude, synthetic, qwen-portal, qwen, gemini, ollama, opencode",
    )
    llm_fallback: str = Field(
        default="",
        description="备用 Provider 列表（逗号分隔，按优先级），如: qwen,ollama",
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
        if self.anthropic_api_key:
            return self.anthropic_api_key

        from lifee.providers.auth import get_api_key_from_credentials
        return get_api_key_from_credentials()

    # Synthetic (免费大模型代理)
    synthetic_model: str = Field(
        default="deepseek-v3",
        description="Synthetic 模型名称 (deepseek-v3, glm-4.7, qwen3-235b 等)",
    )
    synthetic_api_key: str = Field(default="", description="Synthetic API Key")

    # Qwen Portal (免费 OAuth，通过 clawdbot 登录)
    qwen_portal_model: str = Field(default="coder-model", description="Qwen Portal 模型名称")

    # Qwen API (阿里通义千问 DashScope，免费 2000/天)
    qwen_api_key: str = Field(default="", description="Qwen/DashScope API Key")
    qwen_model: str = Field(default="qwen-plus", description="Qwen 模型名称")

    # Gemini API (Google)
    google_api_key: str = Field(default="", description="Google API Key")
    gemini_model: str = Field(default="gemini-2.0-flash", description="Gemini 模型名称")

    # Ollama (本地，完全免费)
    ollama_model: str = Field(default="qwen2.5", description="Ollama 模型名称")
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Ollama API 地址",
    )

    # OpenCode Zen (GLM-4.7 免费)
    opencode_api_key: str = Field(default="", description="OpenCode API Key")
    opencode_model: str = Field(default="glm-4.7", description="OpenCode 模型 (glm-4.7 免费)")

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
