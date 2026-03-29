"""认证模块 - 读取 Claude Code CLI 凭据"""
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Anthropic OAuth 配置（来自 clawdbot/pi-ai）
OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


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


def save_credentials(creds: OAuthCredentials) -> bool:
    """
    保存刷新后的凭据到文件

    Args:
        creds: 新的凭据

    Returns:
        是否保存成功
    """
    cred_path = get_claude_credentials_path()

    if not cred_path.exists():
        return False

    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "claudeAiOauth" not in data:
            return False

        data["claudeAiOauth"]["accessToken"] = creds.access_token
        data["claudeAiOauth"]["expiresAt"] = creds.expires_at
        if creds.refresh_token:
            data["claudeAiOauth"]["refreshToken"] = creds.refresh_token

        with open(cred_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True

    except (json.JSONDecodeError, IOError):
        return False


def refresh_oauth_token(refresh_token: str) -> Optional[OAuthCredentials]:
    """
    使用 refresh token 刷新 OAuth 凭据

    Args:
        refresh_token: 刷新令牌

    Returns:
        新的 OAuthCredentials 或 None（刷新失败）
    """
    payload = json.dumps({
        "grant_type": "refresh_token",
        "client_id": OAUTH_CLIENT_ID,
        "refresh_token": refresh_token,
    }).encode("utf-8")

    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "claude-cli/2.1.2 (external, cli)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        access_token = data.get("access_token")
        new_refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)

        if not access_token:
            return None

        # 计算过期时间（提前 5 分钟）
        expires_at = int(time.time() * 1000) + (expires_in * 1000) - (5 * 60 * 1000)

        return OAuthCredentials(
            access_token=access_token,
            refresh_token=new_refresh_token or refresh_token,
            expires_at=expires_at,
        )

    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        print(f"[警告] Token 刷新失败: {e}")
        return None


def get_api_key_from_credentials() -> Optional[str]:
    """
    从 Claude Code 凭据获取 API Key（access token）

    如果 token 已过期且有 refresh_token，会自动刷新并保存。

    Returns:
        access token 或 None
    """
    creds = read_claude_code_credentials()
    if creds is None:
        return None

    if creds.is_expired:
        if not creds.refresh_token:
            print("[错误] Token 已过期且无 refresh_token，请重新运行 'claude login'")
            return None

        print("[信息] Token 已过期，正在刷新...")
        new_creds = refresh_oauth_token(creds.refresh_token)

        if new_creds is None:
            print("[错误] Token 刷新失败，请重新运行 'claude login'")
            return None

        if save_credentials(new_creds):
            print("[信息] Token 刷新成功，凭据已更新")
        else:
            print("[警告] Token 刷新成功，但无法保存到文件")

        return new_creds.access_token

    return creds.access_token


def get_clawdbot_credentials_path() -> Path:
    """获取 clawdbot 凭据文件路径"""
    return Path.home() / ".clawdbot" / "agents" / "main" / "agent" / "auth-profiles.json"


def read_clawdbot_qwen_credentials() -> Optional[OAuthCredentials]:
    """
    读取 clawdbot 的 Qwen Portal OAuth 凭据

    凭据文件位置: ~/.clawdbot/agents/main/agent/auth-profiles.json

    Returns:
        OAuthCredentials 或 None（如果不存在或无效）
    """
    cred_path = get_clawdbot_credentials_path()

    if not cred_path.exists():
        return None

    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profiles = data.get("profiles", {})

        # 查找 qwen-portal 相关的凭据
        for key, profile in profiles.items():
            if "qwen" in key.lower():
                access_token = profile.get("access")
                refresh_token = profile.get("refresh")
                expires_at = profile.get("expires")

                if access_token:
                    return OAuthCredentials(
                        access_token=access_token,
                        refresh_token=refresh_token,
                        expires_at=int(expires_at) if expires_at else 0,
                        provider="qwen-portal",
                    )

        return None

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def read_clawdbot_synthetic_credentials() -> Optional[str]:
    """
    读取 clawdbot 的 Synthetic API Key

    凭据文件位置: ~/.clawdbot/agents/main/agent/auth-profiles.json

    Returns:
        API Key 或 None
    """
    cred_path = get_clawdbot_credentials_path()

    if not cred_path.exists():
        return None

    try:
        with open(cred_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profiles = data.get("profiles", {})

        # 查找 synthetic 相关的凭据
        for key, profile in profiles.items():
            if "synthetic" in key.lower():
                # Synthetic 可能使用 api_key 或 access 字段
                api_key = profile.get("key") or profile.get("access")
                if api_key:
                    return api_key

        return None

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


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
