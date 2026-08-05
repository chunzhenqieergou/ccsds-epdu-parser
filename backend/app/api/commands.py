"""
遥控指令 CRUD API
=================
提供指令的列表、创建、详情、更新、删除、模拟发送接口。
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..deps import get_current_user, require_operator, log_action, get_db

router = APIRouter()

ROLE_RANK: dict[str, int] = {"observer": 0, "operator": 1, "admin": 2}


def _cmd_out(cmd: models.RemoteCommand) -> schemas.RemoteCommandOut:
    """构建带 satellite_name 的输出，排除模型中不存在的 description 字段"""
    out = schemas.RemoteCommandOut.model_validate(cmd)
    out.satellite_name = cmd.satellite.name if cmd.satellite else None
    return out


def _check_command_permission(
    cmd: models.RemoteCommand, user: models.User
) -> None:
    """校验指令权限：检查 forbidden 标志和 permission_level"""
    if cmd.forbidden == 1:
        raise HTTPException(status_code=403, detail="该指令已被禁止发送")
    user_level = ROLE_RANK.get(user.role, 0)
    if user_level < cmd.permission_level:
        raise HTTPException(status_code=403, detail="权限不足，无法执行该指令")


@router.get("/")
def list_commands(
    satellite_id: int | None = Query(None, description="按卫星过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指令列表，支持卫星过滤和分页"""
    q = db.query(models.RemoteCommand).options(
        joinedload(models.RemoteCommand.satellite)
    )
    if satellite_id:
        q = q.filter(models.RemoteCommand.satellite_id == satellite_id)
    total = q.count()
    commands = (
        q.order_by(models.RemoteCommand.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_cmd_out(c) for c in commands]
    return schemas.ok(
        schemas.PageResult(total=total, page=page, page_size=page_size, items=items)
    )


@router.post("/", status_code=201)
def create_command(
    body: schemas.RemoteCommandCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """创建指令"""
    sat = db.query(models.Satellite).filter(
        models.Satellite.id == body.satellite_id
    ).first()
    if not sat:
        raise HTTPException(status_code=404, detail="卫星不存在")
    cmd_data = body.model_dump(exclude={"description"})
    cmd = models.RemoteCommand(**cmd_data)
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    log_action(
        db, current_user, "创建指令",
        f"command:{cmd.id}",
        f"创建指令 {cmd.cmd_code}({cmd.name})",
        request,
    )
    return schemas.ok(_cmd_out(cmd))


@router.get("/{command_id}")
def get_command(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """指令详情"""
    cmd = db.query(models.RemoteCommand).options(
        joinedload(models.RemoteCommand.satellite)
    ).filter(models.RemoteCommand.id == command_id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="指令不存在")
    return schemas.ok(_cmd_out(cmd))


@router.put("/{command_id}")
def update_command(
    command_id: int,
    body: schemas.RemoteCommandUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """更新指令"""
    cmd = db.query(models.RemoteCommand).filter(
        models.RemoteCommand.id == command_id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="指令不存在")
    update_data = body.model_dump(exclude_unset=True)
    update_data.pop("description", None)
    for key, val in update_data.items():
        setattr(cmd, key, val)
    db.commit()
    db.refresh(cmd)
    log_action(
        db, current_user, "更新指令",
        f"command:{cmd.id}",
        f"更新指令 {cmd.cmd_code}({cmd.name})",
        request,
    )
    return schemas.ok(_cmd_out(cmd))


@router.delete("/{command_id}")
def delete_command(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """删除指令"""
    cmd = db.query(models.RemoteCommand).filter(
        models.RemoteCommand.id == command_id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="指令不存在")
    cmd_code = cmd.cmd_code
    cmd_name = cmd.name
    cid = cmd.id
    db.delete(cmd)
    db.commit()
    log_action(
        db, current_user, "删除指令",
        f"command:{cid}",
        f"删除指令 {cmd_code}({cmd_name})",
        request,
    )
    return schemas.ok(None, "已删除")


@router.post("/send")
def send_command(
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """模拟发送指令：校验权限后记录操作日志并返回发送结果"""
    command_id = body.get("command_id")
    if not command_id:
        raise HTTPException(status_code=400, detail="缺少 command_id")
    cmd = db.query(models.RemoteCommand).filter(
        models.RemoteCommand.id == command_id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="指令不存在")
    _check_command_permission(cmd, current_user)

    ts = datetime.now(timezone.utc).isoformat()
    cmd_params = body.get("params", {})
    log_action(
        db, current_user, "发送指令",
        f"command:{cmd.id}",
        f"发送指令 {cmd.cmd_code} 参数: {cmd_params}",
        request,
    )
    return schemas.ok({
        "sent": True,
        "command_code": cmd.cmd_code,
        "ts": ts,
    })


@router.post("/{command_id}/send")
def send_command_by_id(
    command_id: int,
    body: dict | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """通过路径参数发送指令：校验权限后记录操作日志并返回发送结果"""
    cmd = db.query(models.RemoteCommand).filter(
        models.RemoteCommand.id == command_id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="指令不存在")
    _check_command_permission(cmd, current_user)

    ts = datetime.now(timezone.utc).isoformat()
    cmd_params = body.get("params", {}) if body else {}
    log_action(
        db, current_user, "发送指令",
        f"command:{cmd.id}",
        f"发送指令 {cmd.cmd_code} 参数: {cmd_params}",
        request,
    )
    return schemas.ok({
        "sent": True,
        "command_code": cmd.cmd_code,
        "ts": ts,
    })


@router.post("/{command_id}/execute")
def execute_command(
    command_id: int,
    body: dict | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """指令执行快捷方式：校验权限后记录操作日志并返回执行结果"""
    cmd = db.query(models.RemoteCommand).filter(
        models.RemoteCommand.id == command_id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="指令不存在")
    _check_command_permission(cmd, current_user)

    ts = datetime.now(timezone.utc).isoformat()
    cmd_params = body.get("params", {}) if body else {}
    log_action(
        db, current_user, "执行指令",
        f"command:{cmd.id}",
        f"执行指令 {cmd.cmd_code} 参数: {cmd_params}",
        request,
    )
    return schemas.ok({
        "sent": True,
        "command_code": cmd.cmd_code,
        "ts": ts,
    })
