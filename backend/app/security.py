"""
安全与认证工具
==============
JWT 签发/校验（python-jose）+ 密码哈希（bcrypt 直接调用，规避 passlib 与
bcrypt 5.x 的兼容性问题）。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from .config import settings


# ---------------------------------------------------------------------------
# 密码哈希
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    """bcrypt 加密（自带随机盐）"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(username: str) -> tuple[str, int]:
    """生成 access_token，返回 (token, 有效秒数)"""
    minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    token = _create_token(username, "access", timedelta(minutes=minutes))
    return token, minutes * 60


def create_refresh_token(username: str) -> str:
    """生成 refresh_token"""
    days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    return _create_token(username, "refresh", timedelta(days=days))


def decode_token(token: str, expected_type: Optional[str] = None) -> dict | None:
    """解码并校验 JWT，失败返回 None"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        if expected_type and payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


def get_token_subject(token: str, expected_type: Optional[str] = None) -> str | None:
    """从 Token 中取出用户名（sub），无效返回 None"""
    payload = decode_token(token, expected_type)
    return payload.get("sub") if payload else None