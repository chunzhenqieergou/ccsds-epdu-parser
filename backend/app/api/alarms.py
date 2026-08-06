"""
告警管理 API
===========
告警记录 CRUD、处理、统计汇总。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, require_operator, log_action, get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# 1. 告警列表
# ---------------------------------------------------------------------------
@router.get("", include_in_schema=False)
@router.get("/")
def list_alarms(
    status: Optional[int] = Query(None, description="状态过滤: 0=未处理 1=已处理"),
    level: Optional[str] = Query(None, description="级别过滤: INFO / WARN / CRITICAL"),
    param_id: Optional[int] = Query(None, description="参数ID过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """告警列表（分页，可选 status / level / param_id 过滤，按创建时间倒序）"""
    q = db.query(models.Alarm)
    if status is not None:
        q = q.filter(models.Alarm.status == status)
    if level:
        q = q.filter(models.Alarm.level == level)
    if param_id:
        q = q.filter(models.Alarm.param_id == param_id)

    total = q.count()
    alarms = q.order_by(desc(models.Alarm.created_at)) \
               .offset((page - 1) * page_size) \
               .limit(page_size) \
               .all()

    items = [schemas.AlarmOut.model_validate(a) for a in alarms]
    return schemas.ok(
        schemas.PageResult(total=total, page=page, page_size=page_size, items=items)
    )


# ---------------------------------------------------------------------------
# 2. 告警统计
# ---------------------------------------------------------------------------
def _alarm_stats(db: Session) -> dict:
    """告警统计核心逻辑：按状态和级别汇总数量"""
    status_rows = db.query(
        models.Alarm.status, func.count(models.Alarm.id)
    ).group_by(models.Alarm.status).all()
    by_status = {f"status_{s}": c for s, c in status_rows}

    level_rows = db.query(
        models.Alarm.level, func.count(models.Alarm.id)
    ).group_by(models.Alarm.level).all()
    by_level = {level: count for level, count in level_rows}

    total = db.query(func.count(models.Alarm.id)).scalar() or 0

    return {
        "total": total,
        # 语义化字段：0=未处理 1=已处理（前端看板统计依赖）
        "pending": by_status.get("status_0", 0),
        "handled": by_status.get("status_1", 0),
        "by_status": by_status,
        "by_level": by_level,
    }


@router.get("/summary")
def alarm_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """告警统计：按状态和级别汇总数量"""
    return schemas.ok(_alarm_stats(db))


@router.get("/stats")
def alarm_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """告警统计（前端 alarmApi.stats 调用）：按状态和级别汇总数量"""
    return schemas.ok(_alarm_stats(db))


# ---------------------------------------------------------------------------
# 3. 创建告警
# ---------------------------------------------------------------------------
@router.post("", status_code=201, include_in_schema=False)
@router.post("/", status_code=201)
def create_alarm(
    body: schemas.AlarmCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """创建告警记录（供系统内部触发或手动录入）"""
    param = db.query(models.TelemetryParam).filter(
        models.TelemetryParam.id == body.param_id
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="参数不存在")

    alarm = models.Alarm(**body.model_dump())
    db.add(alarm)
    db.commit()
    db.refresh(alarm)

    log_action(
        db, current_user, "创建告警",
        f"alarm:{alarm.id}",
        f"创建告警 参数{param.param_code}({param.name}) 级别{body.level}",
        request,
    )
    return schemas.ok(schemas.AlarmOut.model_validate(alarm))


# ---------------------------------------------------------------------------
# 4. 告警详情
# ---------------------------------------------------------------------------
@router.get("/{alarm_id}")
def get_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """告警详情"""
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")
    return schemas.ok(schemas.AlarmOut.model_validate(alarm))


# ---------------------------------------------------------------------------
# 5. 处理告警
# ---------------------------------------------------------------------------
@router.put("/{alarm_id}/handle")
def handle_alarm(
    alarm_id: int,
    body: schemas.AlarmHandle,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """处理告警：标记状态并记录处理人和备注"""
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")

    alarm.status = body.status
    alarm.handle_note = body.note
    alarm.handled_by = current_user.id
    alarm.handled_at = datetime.now()
    db.commit()
    db.refresh(alarm)

    log_action(
        db, current_user, "处理告警",
        f"alarm:{alarm.id}",
        f"处理告警 {alarm.id} 状态->{body.status}",
        request,
    )
    return schemas.ok(schemas.AlarmOut.model_validate(alarm))


# ---------------------------------------------------------------------------
# 6. 删除告警
# ---------------------------------------------------------------------------
@router.delete("/{alarm_id}")
def delete_alarm(
    alarm_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """删除告警记录"""
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="告警不存在")

    aid = alarm.id
    db.delete(alarm)
    db.commit()

    log_action(
        db, current_user, "删除告警",
        f"alarm:{aid}",
        f"删除告警 {aid}",
        request,
    )
    return schemas.ok(None, "已删除")
