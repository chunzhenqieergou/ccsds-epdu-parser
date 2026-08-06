"""
遥测数据查询 API
===============
历史数据查询（含自动抽样）、最新值、整帧列表、模拟器数据接口、实时 SSE 推送。
"""
import asyncio
import json
import math
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db
from ..database import get_db as _get_db
from ..security import get_token_subject
from ..services.sse import event_stream_generator, sse_subscribe
from ..tsdb import get_tsdb_store

router = APIRouter()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _parse_datetime(value: Optional[str], label: str) -> Optional[datetime]:
    """解析 ISO 格式时间字符串"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 时间格式无效，需 ISO 格式")


def _split_codes(raw: Optional[str]) -> list[str]:
    """逗号分隔参数字符串 -> 去空列表"""
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def _downsample_per_param(data: list, max_points: int) -> list:
    """按参数分组等间隔降采样，使总点数不超过 max_points"""
    if not data:
        return []

    groups: dict[str, list] = defaultdict(list)
    for d in data:
        groups[d.param_code].append(d)

    num_groups = len(groups)
    per_group = max(max_points // num_groups, 1)

    result: list = []
    for code, group in groups.items():
        n = len(group)
        if n <= per_group:
            result.extend(group)
        else:
            step = (n - 1) / (per_group - 1) if per_group > 1 else n
            for i in range(per_group):
                idx = min(int(round(i * step)), n - 1)
                result.append(group[idx])

    result.sort(key=lambda d: d.ts)
    return result


def _point_dict(d) -> dict:
    """TelemetryData -> 输出字典"""
    return {
        "ts": d.ts.isoformat(),
        "param_code": d.param_code,
        "raw_value": d.raw_value,
        "value": d.value,
        "quality": d.quality,
    }


# ---------------------------------------------------------------------------
# 1. 历史数据查询（核心）
# ---------------------------------------------------------------------------
@router.get("/query")
def query_telemetry(
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    param_codes: Optional[str] = Query(None, description="参数代号，逗号分隔，空=全部"),
    channel_id: Optional[int] = Query(None, description="通道ID筛选"),
    start: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    sampling: Optional[str] = Query(None, pattern="^(full|auto)$", description="抽样模式: full / auto"),
    max_points: int = Query(1000, ge=100, le=50000, description="自动抽样最大点数"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """历史数据查询：时间范围 / 参数多选 / 分页 / 自动抽样 / 通道筛选"""
    start_dt = _parse_datetime(start, "start")
    end_dt = _parse_datetime(end, "end")
    codes = _split_codes(param_codes)

    tsdb = get_tsdb_store()
    ch_ids: Optional[list[int]] = [channel_id] if channel_id else None

    # 自动抽样模式：全量查询 → 按参数分组降采样
    if sampling == "auto":
        all_data = tsdb.query_all(
            satellite_id=satellite_id, param_codes=codes, channel_ids=ch_ids,
            start_dt=start_dt, end_dt=end_dt,
        )
        sampled = _downsample_per_param(all_data, max_points)
        return schemas.ok({
            "total": len(all_data),
            "points": [_point_dict(d) for d in sampled],
        })

    # 普通分页模式
    total, rows = tsdb.query(
        satellite_id=satellite_id, param_codes=codes, channel_ids=ch_ids,
        start_dt=start_dt, end_dt=end_dt, page=page, page_size=page_size,
    )

    return schemas.ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "points": [_point_dict(r) for r in rows],
    })


# ---------------------------------------------------------------------------
# 2. 最新值查询
# ---------------------------------------------------------------------------
@router.get("/latest")
def latest_values(
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    param_codes: Optional[str] = Query(None, description="参数代号，逗号分隔"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """获取每个参数的最新值（每个 param_code 取最新一条）"""
    codes = _split_codes(param_codes)

    tsdb = get_tsdb_store()
    rows = tsdb.latest(satellite_id=satellite_id, param_codes=codes)

    return schemas.ok([_point_dict(r) for r in rows])


# ---------------------------------------------------------------------------
# 3. 整帧列表
# ---------------------------------------------------------------------------
@router.get("/frames")
def list_frames(
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    protocol_type: Optional[str] = Query(None, description="协议类型筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """整帧列表分页，可选 protocol_type 过滤"""
    q = db.query(models.TelemetryFrame)
    if satellite_id:
        q = q.filter(models.TelemetryFrame.satellite_id == satellite_id)
    if protocol_type:
        q = q.filter(models.TelemetryFrame.protocol_type == protocol_type)

    total = q.count()
    frames = q.order_by(desc(models.TelemetryFrame.ts)) \
               .offset((page - 1) * page_size) \
               .limit(page_size) \
               .all()

    items = [
        schemas.FrameOut(
            id=f.id,
            ts=f.ts,
            satellite_id=f.satellite_id,
            channel_id=f.channel_id,
            protocol_type=f.protocol_type,
            apid=f.apid,
            raw_hex=f.raw_hex,
            frame_size=f.frame_size,
        )
        for f in frames
    ]
    return schemas.ok(
        schemas.PageResult(total=total, page=page, page_size=page_size, items=items)
    )


# ---------------------------------------------------------------------------
# 4. 模拟器数据查询
# ---------------------------------------------------------------------------
@router.get("/simulate")
def simulate_telemetry(
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    param_codes: Optional[str] = Query(None, description="参数代号，逗号分隔"),
    start: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """模拟器数据查询：返回原始值 / 工程值及对应参数的 min/max 阈值提示"""
    start_dt = _parse_datetime(start, "start")
    end_dt = _parse_datetime(end, "end")
    codes = _split_codes(param_codes)

    # 查询参数阈值信息
    param_thresholds: dict[str, dict] = {}
    if codes:
        params = db.query(models.TelemetryParam).filter(
            models.TelemetryParam.param_code.in_(codes)
        ).all()
        for p in params:
            param_thresholds[p.param_code] = {
                "min": p.threshold_min,
                "max": p.threshold_max,
                "unit": p.unit,
                "name": p.name,
            }

    tsdb = get_tsdb_store()
    total, rows = tsdb.query(
        satellite_id=satellite_id, param_codes=codes, channel_ids=None,
        start_dt=start_dt, end_dt=end_dt, page=page, page_size=page_size,
    )

    points = []
    for d in rows:
        pt = param_thresholds.get(d.param_code, {})
        points.append({
            "ts": d.ts.isoformat(),
            "param_code": d.param_code,
            "raw_value": d.raw_value,
            "value": d.value,
            "quality": d.quality,
            "threshold_min": pt.get("min"),
            "threshold_max": pt.get("max"),
            "unit": pt.get("unit", ""),
            "param_name": pt.get("name", ""),
        })

    return schemas.ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "points": points,
    })


# ---------------------------------------------------------------------------
# 5. 实时值（复用 latest 逻辑）
# ---------------------------------------------------------------------------
@router.get("/realtime")
def realtime(
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    param_codes: Optional[str] = Query(None, description="参数代号，逗号分隔"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """获取每个参数的最新值（与 /latest 逻辑相同，供前端 realtime 调用）"""
    codes = _split_codes(param_codes)

    tsdb = get_tsdb_store()
    rows = tsdb.latest(satellite_id=satellite_id, param_codes=codes)

    return schemas.ok([_point_dict(r) for r in rows])


# ---------------------------------------------------------------------------
# 6. 单帧详情
# ---------------------------------------------------------------------------
@router.get("/frames/{frame_id}")
def get_frame(
    frame_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    frame = db.query(models.TelemetryFrame).filter(
        models.TelemetryFrame.id == frame_id
    ).first()
    if not frame:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帧不存在")

    return schemas.ok(
        schemas.FrameOut(
            id=frame.id,
            ts=frame.ts,
            satellite_id=frame.satellite_id,
            channel_id=frame.channel_id,
            protocol_type=frame.protocol_type,
            apid=frame.apid,
            raw_hex=frame.raw_hex,
            frame_size=frame.frame_size,
        )
    )


# ---------------------------------------------------------------------------
# 7. SSE 实时推送
# ---------------------------------------------------------------------------
@router.get("/sse")
async def sse_endpoint(
    request: Request,
    satellite_id: Optional[int] = Query(None),
    token: str = Query(...),
):
    username = get_token_subject(token, "access")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SSE 令牌无效或已过期",
        )

    db = _get_db().__next__()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SSE 用户不存在",
            )
        if user.status != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SSE 账号已被禁用",
            )
    finally:
        db.close()

    subscriber_queue, unsubscribe = sse_subscribe()

    async def _generator():
        try:
            async for msg in event_stream_generator(subscriber_queue):
                yield msg
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe()

    try:
        from sse_starlette.sse import EventSourceResponse
        return EventSourceResponse(_generator(), media_type="text/event-stream")
    except ImportError:
        from fastapi.responses import StreamingResponse

        async def _raw_generator():
            async for msg in _generator():
                event = msg.get("event", "")
                data = msg.get("data", "")
                yield f"event: {event}\ndata: {data}\n\n"

        return StreamingResponse(
            _raw_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
