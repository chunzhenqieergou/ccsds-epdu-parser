"""
系统管理 API 路由
================
提供用户管理（CRUD）、角色定义、操作日志查询、系统校时。
管理类操作需要 admin 角色。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, log_action, require_admin
from ..security import hash_password

router = APIRouter()


# ---------------------------------------------------------------------------
# 用户列表（分页 + 关键字搜索）
# ---------------------------------------------------------------------------
@router.get("/users")
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    username: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    q = db.query(models.User)
    if username:
        q = q.filter(models.User.username.contains(username))
    total = q.count()
    users = (
        q.order_by(models.User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.ok(data=schemas.PageResult[schemas.UserOut](
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.UserOut.model_validate(u) for u in users],
    ))


# ---------------------------------------------------------------------------
# 管理员创建用户
# ---------------------------------------------------------------------------
@router.post("/users")
def create_user(
    data: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        email=data.email,
        remark=data.remark,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(db, current_user, "create_user", target="user",
               detail=f"管理员创建用户 {user.username}（角色 {user.role}）", request=request)
    return schemas.ok(data=schemas.UserOut.model_validate(user))


# ---------------------------------------------------------------------------
# 修改用户
# ---------------------------------------------------------------------------
@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if data.role is not None:
        target.role = data.role
    if data.status is not None:
        target.status = data.status
    if data.email is not None:
        target.email = data.email
    if data.remark is not None:
        target.remark = data.remark
    if data.password is not None:
        target.password_hash = hash_password(data.password)

    db.commit()
    db.refresh(target)

    log_action(db, current_user, "update_user", target="user",
               detail=f"修改用户 {target.username}", request=request)
    return schemas.ok(data=schemas.UserOut.model_validate(target))


# ---------------------------------------------------------------------------
# 删除用户（禁止删除自己）
# ---------------------------------------------------------------------------
@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己")

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    deleted_username = target.username
    db.delete(target)
    db.commit()

    log_action(db, current_user, "delete_user", target="user",
               detail=f"删除用户 {deleted_username}", request=request)
    return schemas.ok(message=f"用户 {deleted_username} 已删除")


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return schemas.ok(data=schemas.UserOut.model_validate(target))


# ---------------------------------------------------------------------------
# 角色定义
# ---------------------------------------------------------------------------
ROLE_DEFINITIONS = [
    schemas.RoleOut(
        name="admin",
        label="管理员",
        permissions=["*"],
    ),
    schemas.RoleOut(
        name="operator",
        label="操作员",
        permissions=[
            "satellite:read", "satellite:write",
            "telemetry:read",
            "param:read", "param:write",
            "channel:read", "channel:write",
            "command:read", "command:write",
            "alarm:read", "alarm:handle",
            "export:all",
            "statistics:all",
        ],
    ),
    schemas.RoleOut(
        name="observer",
        label="观察员",
        permissions=[
            "satellite:read",
            "telemetry:read",
            "param:read",
            "channel:read",
            "command:read",
            "alarm:read",
            "export:all",
            "statistics:all",
        ],
    ),
]


@router.get("/roles")
def get_roles():
    return schemas.ok(data=ROLE_DEFINITIONS)


@router.put("/roles/{role_name}")
def update_role(
    role_name: str,
    data: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return schemas.ok(data=True)


@router.get("/logs/stats")
def logs_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    total_n = db.query(models.OperationLog).count()
    rows = db.query(
        models.OperationLog.action,
        func.count(models.OperationLog.id).label("cnt"),
    ).group_by(models.OperationLog.action).all()
    by_action = {row.action: row.cnt for row in rows}
    return schemas.ok(data={"totalN": total_n, "by_action": by_action})


# ---------------------------------------------------------------------------
# 操作日志（分页 + 筛选）
# ---------------------------------------------------------------------------
@router.get("/logs")
def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    username: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    q = db.query(models.OperationLog)
    if action:
        q = q.filter(models.OperationLog.action == action)
    if username:
        q = q.filter(models.OperationLog.username.contains(username))
    if start:
        q = q.filter(models.OperationLog.created_at >= start)
    if end:
        q = q.filter(models.OperationLog.created_at <= end)

    total = q.count()
    logs = (
        q.order_by(models.OperationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.ok(data=schemas.PageResult[schemas.OperationLogOut](
        total=total,
        page=page,
        page_size=page_size,
        items=[schemas.OperationLogOut.model_validate(log) for log in logs],
    ))


# ---------------------------------------------------------------------------
# 系统校时
# ---------------------------------------------------------------------------
@router.get("/time")
def server_time():
    return schemas.ok(data={"server_time": datetime.now(timezone.utc)})
