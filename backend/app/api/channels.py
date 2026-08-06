"""
数据接收通道 CRUD API
=====================
提供通道的列表、创建、详情、更新、删除接口。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..deps import get_current_user, require_operator, log_action, get_db
from ..receiver.server import real_receiver

router = APIRouter()

VALID_PROTOCOLS = {"CCSDS", "1553B", "CAN", "RS422"}


def _channel_out(channel: models.Channel) -> schemas.ChannelOut:
    """构建带 satellite_name 的输出"""
    out = schemas.ChannelOut.model_validate(channel)
    out.satellite_name = channel.satellite.name if channel.satellite else None
    return out


@router.get("", include_in_schema=False)
@router.get("/")
def list_channels(
    satellite_id: int | None = Query(None, description="按卫星过滤"),
    protocol_type: str | None = Query(None, description="按协议类型过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """通道列表，支持卫星/协议类型过滤和分页"""
    q = db.query(models.Channel).options(
        joinedload(models.Channel.satellite)
    )
    if satellite_id:
        q = q.filter(models.Channel.satellite_id == satellite_id)
    if protocol_type:
        if protocol_type not in VALID_PROTOCOLS:
            raise HTTPException(
                status_code=400,
                detail=f"无效的协议类型，支持: {', '.join(sorted(VALID_PROTOCOLS))}",
            )
        q = q.filter(models.Channel.protocol_type == protocol_type)
    total = q.count()
    channels = (
        q.order_by(models.Channel.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_channel_out(c) for c in channels]
    return schemas.ok(
        schemas.PageResult(total=total, page=page, page_size=page_size, items=items)
    )


@router.post("", status_code=201, include_in_schema=False)
@router.post("/", status_code=201)
def create_channel(
    body: schemas.ChannelCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """创建通道"""
    sat = db.query(models.Satellite).filter(
        models.Satellite.id == body.satellite_id
    ).first()
    if not sat:
        raise HTTPException(status_code=404, detail="卫星不存在")
    if body.protocol_type not in VALID_PROTOCOLS:
        raise HTTPException(
            status_code=400,
            detail=f"无效的协议类型，支持: {', '.join(sorted(VALID_PROTOCOLS))}",
        )
    channel = models.Channel(**body.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    log_action(
        db, current_user, "创建通道",
        f"channel:{channel.id}",
        f"创建通道 {channel.name}({channel.protocol_type})",
        request,
    )
    return schemas.ok(_channel_out(channel))


@router.post("/{channel_id}/start")
def start_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """启动通道"""
    channel = db.query(models.Channel).filter(
        models.Channel.id == channel_id
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    channel.running = 1
    db.commit()
    db.refresh(channel)
    # 联动真实接收器：恢复接收该协议帧
    real_receiver.set_protocol_enabled(channel.protocol_type, True)
    log_action(
        db, current_user, "启动通道",
        f"channel:{channel.id}",
        f"启动通道 {channel.name}",
        request,
    )
    return schemas.ok(_channel_out(channel))


@router.post("/{channel_id}/stop")
def stop_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """停止通道"""
    channel = db.query(models.Channel).filter(
        models.Channel.id == channel_id
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    channel.running = 0
    db.commit()
    db.refresh(channel)
    # 联动真实接收器：停止接收该协议帧
    real_receiver.set_protocol_enabled(channel.protocol_type, False)
    log_action(
        db, current_user, "停止通道",
        f"channel:{channel.id}",
        f"停止通道 {channel.name}",
        request,
    )
    return schemas.ok(_channel_out(channel))


@router.get("/{channel_id}")
def get_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """通道详情"""
    channel = db.query(models.Channel).options(
        joinedload(models.Channel.satellite)
    ).filter(models.Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    return schemas.ok(_channel_out(channel))


@router.put("/{channel_id}")
def update_channel(
    channel_id: int,
    body: schemas.ChannelUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """更新通道"""
    channel = db.query(models.Channel).filter(
        models.Channel.id == channel_id
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    if body.protocol_type is not None and body.protocol_type not in VALID_PROTOCOLS:
        raise HTTPException(
            status_code=400,
            detail=f"无效的协议类型，支持: {', '.join(sorted(VALID_PROTOCOLS))}",
        )
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(channel, key, val)
    db.commit()
    db.refresh(channel)
    log_action(
        db, current_user, "更新通道",
        f"channel:{channel.id}",
        f"更新通道 {channel.name}({channel.protocol_type})",
        request,
    )
    return schemas.ok(_channel_out(channel))


@router.delete("/{channel_id}")
def delete_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """删除通道"""
    channel = db.query(models.Channel).filter(
        models.Channel.id == channel_id
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="通道不存在")
    ch_name = channel.name
    ch_id = channel.id
    db.delete(channel)
    db.commit()
    log_action(
        db, current_user, "删除通道",
        f"channel:{ch_id}",
        f"删除通道 {ch_name}",
        request,
    )
    return schemas.ok(None, "已删除")
