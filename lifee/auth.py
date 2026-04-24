"""LIFEE Auth —— 自家 email+password+OTP 验证，签 JWT 放 cookie。

依赖：bcrypt（密码），PyJWT（token），httpx（发邮件，已有）。
环境变量：
  JWT_SECRET         —— 必填。用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成
  JWT_TTL_DAYS       —— 可选，默认 30
  AUTH_COOKIE_NAME   —— 可选，默认 `lifee_auth`
  RESEND_API_KEY     —— 可选。不设置则 OTP 直接打印到日志，方便本地开发
  RESEND_FROM        —— 可选，默认 `LIFEE <onboarding@resend.dev>`
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

import bcrypt
import httpx
import jwt

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

_JWT_SECRET = os.getenv("JWT_SECRET", "").strip('"')
_JWT_TTL_DAYS = int(os.getenv("JWT_TTL_DAYS", "30"))
_JWT_ALGO = "HS256"
_AUTH_COOKIE = os.getenv("AUTH_COOKIE_NAME", "lifee_auth")

_RESEND_KEY = os.getenv("RESEND_API_KEY", "").strip('"')
_RESEND_FROM = os.getenv("RESEND_FROM", "LIFEE <onboarding@resend.dev>").strip('"')

# 发邮件用的 httpx client（复用连接）
_mail_client: httpx.AsyncClient | None = None


def _get_mail_client() -> httpx.AsyncClient:
    global _mail_client
    if _mail_client is None or _mail_client.is_closed:
        _mail_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    return _mail_client


# --------------------------------------------------------------------------- #
# 密码
# --------------------------------------------------------------------------- #


def hash_password(pw: str) -> str:
    """bcrypt 12 round。cost 12 在 2C 轻量上 ~200ms，登录体感没问题。"""
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #


def _assert_secret() -> str:
    if not _JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET 未设置。生成：python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return _JWT_SECRET


def make_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + _JWT_TTL_DAYS * 86400,
    }
    return jwt.encode(payload, _assert_secret(), algorithm=_JWT_ALGO)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, _assert_secret(), algorithms=[_JWT_ALGO])
    except jwt.PyJWTError:
        return None


def cookie_name() -> str:
    return _AUTH_COOKIE


def cookie_max_age() -> int:
    return _JWT_TTL_DAYS * 86400


# --------------------------------------------------------------------------- #
# 邮件发送（Resend）
# --------------------------------------------------------------------------- #


async def send_otp_email(email: str, code: str, purpose: str) -> bool:
    """发 OTP 到邮箱。RESEND_API_KEY 未设置时打印到日志并返回 True（方便本地/初期）。"""
    subject = "Your LIFEE verification code" if purpose == "signup" else "Reset your LIFEE password"
    intro = (
        "Welcome to LIFEE. Use the code below to finish signing up."
        if purpose == "signup"
        else "Use the code below to reset your password."
    )
    html = (
        f"<div style=\"font-family: system-ui, sans-serif; max-width: 420px; margin: 0 auto; padding: 24px;\">"
        f"<h2 style=\"font-weight: 600;\">LIFEE</h2>"
        f"<p style=\"color: #555;\">{intro}</p>"
        f"<p style=\"font-size: 32px; letter-spacing: 8px; font-weight: 700; margin: 24px 0;\">{code}</p>"
        f"<p style=\"color: #999; font-size: 13px;\">This code expires in 10 minutes. If you didn't request it, ignore this email.</p>"
        f"</div>"
    )

    if not _RESEND_KEY:
        print(f"[auth] RESEND_API_KEY 未配置 —— OTP for {email} ({purpose}): {code}")
        return True

    try:
        r = await _get_mail_client().post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {_RESEND_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": _RESEND_FROM,
                "to": [email],
                "subject": subject,
                "html": html,
            },
        )
        if r.status_code >= 400:
            print(f"[auth] Resend send failed {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[auth] Resend exception: {type(e).__name__}: {e}")
        return False


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def random_password(n: int = 16) -> str:
    return secrets.token_urlsafe(n)
