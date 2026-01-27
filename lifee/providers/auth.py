"""认证模块 - 读取 Claude Code CLI 凭据"""
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass
class OAuthCredentials:
    """OAuth 凭据"""
    access_token: str
    refresh_token: Optional[str]
    expires_at: int  # 毫秒时间戳
    provider: str = "anthropic"

    @property
    def is_expired(self) -> bool:
        """检查是否过期（提前 5 分钟）"""
        return time.time() * 1000 > (self.expires_at - 5 * 60 * 1000)

    @property
    def expires_in_seconds(self) -> int:
        """距离过期的秒数"""
        return max(0, int((self.expires_at - time.time() * 1000) / 1000))


def get_claude_credentials_path() -> Path:
    """获取 Claude Code 凭据文件路径"""
    return Path.home() / ".claude" / ".credentials.json"


def read_claude_code_credentials() -> Optional[OAuthCredentials]:
    """
    读取 Claude Code CLI 的 OAuth 凭据

    凭据文件位置: ~/.claude/.credentials.json

    Returns:
        OAuthCredentials 或 None（如果不存在或无效）
    """
    cred_path = get_claude_credentials_path()

    if not cred_path.exists():
        return None

    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        oauth = data.get("claudeAiOauth")
        if not oauth or not isinstance(oauth, dict):
            return None

        access_token = oauth.get("accessToken")
        refresh_token = oauth.get("refreshToken")
        expires_at = oauth.get("expiresAt")

        if not access_token or not isinstance(access_token, str):
            return None

        if not expires_at or not isinstance(expires_at, (int, float)):
            return None

        return OAuthCredentials(
            access_token=access_token,
            refresh_token=refresh_token if isinstance(refresh_token, str) else None,
            expires_at=int(expires_at),
        )

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def get_api_key_from_credentials() -> Optional[str]:
    """
    从 Claude Code 凭据获取 API Key（access token）

    Returns:
        access token 或 None
    """
    creds = read_claude_code_credentials()
    if creds is None:
        return None

    if creds.is_expired:
        # TODO: 实现 token 刷新
        return None

    return creds.access_token


def get_auth_info() -> dict:
    """
    获取认证信息摘要

    Returns:
        包含认证状态的字典
    """
    creds = read_claude_code_credentials()

    if creds is None:
        return {
            "authenticated": False,
            "source": None,
            "message": "未找到 Claude Code 凭据，请先运行 'claude login' 或设置 ANTHROPIC_API_KEY",
        }

    if creds.is_expired:
        return {
            "authenticated": False,
            "source": "claude-code",
            "message": "Claude Code 凭据已过期，请重新运行 'claude login'",
        }

    return {
        "authenticated": True,
        "source": "claude-code",
        "expires_in": creds.expires_in_seconds,
        "message": f"使用 Claude Code OAuth 凭据（{creds.expires_in_seconds // 3600}小时后过期）",
    }
