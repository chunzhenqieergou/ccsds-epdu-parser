"""
FastAPI 依赖注入
===============
数据库会话、当前用户、角色权限控制、操作日志记录等通用依赖。
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import get_token_subject

bearer_scheme = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    def __init__(self, detail: str = "认证失败", code: int = 401):
        super().__init__(status_code=code, detail=detail)


# ---------------------------------------------------------------------------
# 获取当前用户
# ---------------------------------------------------------------------------
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌")

    username = get_token_subject(credentials.credentials, "access")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


# ---------------------------------------------------------------------------
# 角色权限依赖
# ---------------------------------------------------------------------------
ROLE_RANK = {"observer": 1, "operator": 2, "admin": 3}


def require_role(role: str):
    """要求用户具备指定角色及以上权限"""

    def _checker(user: models.User = Depends(get_current_user)) -> models.User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK.get(role, 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="权限不足，需要更高角色")
        return user

    return _checker


require_operator = require_role("operator")
require_admin = require_role("admin")


# ---------------------------------------------------------------------------
# 操作日志记录
# ---------------------------------------------------------------------------
def log_action(db: Session, user: models.User, action: str,
               target: str | None = None, detail: str | None = None,
               request: Request | None = None) -> None:
    """写入操作日志"""
    from .models import OperationLog

    ip = None
    if request is not None:
        ip = request.client.host if request.client else None
    entry = OperationLog(
        user_id=user.id,
        username=user.username,
        action=action,
        target=target,
        detail=detail,
        ip_address=ip,
    )
    db.add(entry)
    db.commit()