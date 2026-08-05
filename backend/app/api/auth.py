"""
认证 API 路由
============
提供注册、登录、登出、Token 刷新、修改密码、获取当前用户信息。
所有操作均记录到 operation_logs。
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, log_action
from ..security import (
    _create_token,
    create_access_token,
    create_refresh_token,
    get_token_subject,
    hash_password,
    verify_password,
)

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
@router.post("/register")
def register(
    data: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    effective_role = "observer"
    if credentials is not None:
        caller_username = get_token_subject(credentials.credentials, "access")
        if caller_username:
            caller = db.query(models.User).filter(
                models.User.username == caller_username
            ).first()
            if caller and caller.role == models.ROLE_ADMIN:
                effective_role = data.role

    user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=effective_role,
        email=data.email,
        remark=data.remark,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, user, "register", target="user",
               detail=f"注册用户 {user.username}（角色 {user.role}）", request=request)
    return schemas.ok(data=schemas.UserOut.model_validate(user))


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------
@router.post("/login")
def login(
    data: schemas.UserLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    user.last_login_at = datetime.now()
    db.commit()
    db.refresh(user)

    if data.remember:
        minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 2
        access_token = _create_token(user.username, "access", timedelta(minutes=minutes))
        expires_in = minutes * 60
    else:
        access_token, expires_in = create_access_token(user.username)

    refresh_token = create_refresh_token(user.username)

    log_action(db, user, "login", target="user", detail="用户登录", request=request)
    return schemas.ok(data=schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=schemas.UserOut.model_validate(user),
    ))


# ---------------------------------------------------------------------------
# 刷新令牌
# ---------------------------------------------------------------------------
@router.post("/refresh")
def refresh_token(
    req: schemas.RefreshRequest,
    db: Session = Depends(get_db),
):
    username = get_token_subject(req.refresh_token, "refresh")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效或已过期")

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.status != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    access_token, expires_in = create_access_token(user.username)
    new_refresh_token = create_refresh_token(user.username)

    return schemas.ok(data=schemas.TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
        user=schemas.UserOut.model_validate(user),
    ))


# ---------------------------------------------------------------------------
# 登出
# ---------------------------------------------------------------------------
@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    log_action(db, current_user, "logout", target="user",
               detail="用户登出", request=request)
    return schemas.ok()


# ---------------------------------------------------------------------------
# 获取当前用户
# ---------------------------------------------------------------------------
@router.get("/me")
def get_me(
    current_user: models.User = Depends(get_current_user),
):
    return schemas.ok(data=schemas.UserOut.model_validate(current_user))


# ---------------------------------------------------------------------------
# 修改密码
# ---------------------------------------------------------------------------
@router.post("/change-password")
def change_password(
    data: schemas.PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

    current_user.password_hash = hash_password(data.new_password)
    db.commit()

    log_action(db, current_user, "change_password", target="user",
               detail="修改密码", request=request)
    return schemas.ok(message="密码修改成功")


@router.put("/change-password")
def change_password_put(
    data: schemas.PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

    current_user.password_hash = hash_password(data.new_password)
    db.commit()

    log_action(db, current_user, "change_password", target="user",
               detail="修改密码", request=request)
    return schemas.ok(message="密码修改成功")
