"""
统计分析 API
===========
基本统计、趋势分析（线性回归）、异常检测（阈值越界）、阶段对比。
同时提供 GET（Query 参数）与 POST（JSON Body）两种调用方式。
"""
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _parse_dt(value: Optional[str], label: str) -> Optional[datetime]:
    """解析 ISO 时间"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 时间格式无效，需 ISO 格式")


def _calc_stats(values: list[float]) -> dict:
    """计算基本统计量：count / min / max / mean / variance / std / diff"""
    n = len(values)
    if n == 0:
        return {
            "count": 0, "min": None, "max": None, "mean": None,
            "variance": None, "std": None, "diff": None,
        }
    mean_val = sum(values) / n
    min_val = min(values)
    max_val = max(values)
    variance = sum((v - mean_val) ** 2 for v in values) / n
    std_val = math.sqrt(variance)
    diff = max_val - min_val
    return {
        "count": n, "min": min_val, "max": max_val,
        "mean": mean_val, "variance": variance,
        "std": std_val, "diff": diff,
    }


def _query_values(
    db: Session,
    param_code: str,
    satellite_id: Optional[int],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> list[float]:
    """按条件查询遥测数据工程值列表"""
    q = db.query(models.TelemetryData.value).filter(
        models.TelemetryData.param_code == param_code
    )
    if satellite_id:
        q = q.filter(models.TelemetryData.satellite_id == satellite_id)
    if start_dt:
        q = q.filter(models.TelemetryData.ts >= start_dt)
    if end_dt:
        q = q.filter(models.TelemetryData.ts <= end_dt)
    return [row[0] for row in q.all()]


def _query_values_with_ts(
    db: Session,
    param_code: str,
    satellite_id: Optional[int],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> list[tuple[datetime, float]]:
    """按条件查询遥测数据（时间戳 + 工程值），按时间升序"""
    q = db.query(models.TelemetryData.ts, models.TelemetryData.value).filter(
        models.TelemetryData.param_code == param_code
    )
    if satellite_id:
        q = q.filter(models.TelemetryData.satellite_id == satellite_id)
    if start_dt:
        q = q.filter(models.TelemetryData.ts >= start_dt)
    if end_dt:
        q = q.filter(models.TelemetryData.ts <= end_dt)
    return q.order_by(models.TelemetryData.ts.asc()).all()


# ---------------------------------------------------------------------------
# 核心逻辑（GET / POST 共用）
# ---------------------------------------------------------------------------
def _do_basic_stats(
    db: Session,
    param_code: str,
    satellite_id: Optional[int],
    start: Optional[str],
    end: Optional[str],
):
    start_dt = _parse_dt(start, "start")
    end_dt = _parse_dt(end, "end")
    values = _query_values(db, param_code, satellite_id, start_dt, end_dt)
    s = _calc_stats(values)
    return schemas.BasicStats(
        param_code=param_code,
        count=s["count"],
        min=s["min"],
        max=s["max"],
        mean=s["mean"],
        variance=s["variance"],
        std=s["std"],
        diff=s["diff"],
    )


def _do_trend_analysis(
    db: Session,
    param_code: str,
    satellite_id: Optional[int],
    start: Optional[str],
    end: Optional[str],
) -> schemas.TrendResult:
    start_dt = _parse_dt(start, "start")
    end_dt = _parse_dt(end, "end")
    rows = _query_values_with_ts(db, param_code, satellite_id, start_dt, end_dt)
    n = len(rows)

    if n < 2:
        first_val = rows[0][1] if n else 0.0
        last_val = rows[-1][1] if n else 0.0
        return schemas.TrendResult(
            param_code=param_code,
            slope=0.0,
            trend="数据不足" if n < 2 else "平稳",
            last_value=last_val,
            first_value=first_val,
            change_percent=0.0,
        )

    t0 = rows[0][0].timestamp()
    xs = [r[0].timestamp() - t0 for r in rows]
    ys = [r[1] for r in rows]

    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)

    denominator = n * sum_xx - sum_x * sum_x
    slope = (n * sum_xy - sum_x * sum_y) / denominator if denominator != 0 else 0.0

    mean_y = sum_y / n if n else 0.0
    rel_slope = abs(slope * n) / abs(mean_y) if mean_y != 0 else abs(slope)

    if rel_slope < 1e-4:
        trend = "平稳"
    elif slope > 0:
        trend = "上升"
    else:
        trend = "下降"

    first_val = ys[0]
    last_val = ys[-1]
    if first_val != 0:
        change_pct = round((last_val - first_val) / abs(first_val) * 100, 4)
    else:
        change_pct = 0.0

    return schemas.TrendResult(
        param_code=param_code,
        slope=round(slope, 8),
        trend=trend,
        last_value=last_val,
        first_value=first_val,
        change_percent=change_pct,
    )


def _do_anomalies(
    db: Session,
    param_code: str,
    satellite_id: Optional[int],
    start: Optional[str],
    end: Optional[str],
    threshold_min: Optional[float],
    threshold_max: Optional[float],
) -> list[schemas.Anomaly]:
    param = db.query(models.TelemetryParam).filter(
        models.TelemetryParam.param_code == param_code
    ).first()

    t_min = threshold_min
    t_max = threshold_max
    if param:
        if t_min is None:
            t_min = param.threshold_min
        if t_max is None:
            t_max = param.threshold_max

    start_dt = _parse_dt(start, "start")
    end_dt = _parse_dt(end, "end")

    q = db.query(models.TelemetryData).filter(
        models.TelemetryData.param_code == param_code
    )
    if satellite_id:
        q = q.filter(models.TelemetryData.satellite_id == satellite_id)
    if start_dt:
        q = q.filter(models.TelemetryData.ts >= start_dt)
    if end_dt:
        q = q.filter(models.TelemetryData.ts <= end_dt)
    rows = q.order_by(models.TelemetryData.ts.asc()).all()

    result: list[schemas.Anomaly] = []
    for r in rows:
        if t_min is not None and r.value < t_min:
            result.append(schemas.Anomaly(
                ts=r.ts,
                param_code=r.param_code,
                value=r.value,
                type="low",
                threshold=t_min,
            ))
        elif t_max is not None and r.value > t_max:
            result.append(schemas.Anomaly(
                ts=r.ts,
                param_code=r.param_code,
                value=r.value,
                type="high",
                threshold=t_max,
            ))

    return result


def _do_compare(
    db: Session,
    param_code: str,
    satellite_id: Optional[int],
    period1_start: Optional[str],
    period1_end: Optional[str],
    period2_start: Optional[str],
    period2_end: Optional[str],
) -> schemas.CompareResult:
    def _period_values(s_start: Optional[str], s_end: Optional[str]) -> list[float]:
        s_dt = _parse_dt(s_start, "period_start")
        e_dt = _parse_dt(s_end, "period_end")
        return _query_values(db, param_code, satellite_id, s_dt, e_dt)

    vals1 = _period_values(period1_start, period1_end)
    vals2 = _period_values(period2_start, period2_end)

    s1 = _calc_stats(vals1)
    s2 = _calc_stats(vals2)

    delta = None
    if s1["mean"] is not None and s2["mean"] is not None:
        delta = round(s2["mean"] - s1["mean"], 6)

    return schemas.CompareResult(
        param_code=param_code,
        periods=[
            schemas.PeriodCompare(
                param_code=param_code,
                period_name="period1",
                mean=s1["mean"],
                max=s1["max"],
                min=s1["min"],
                std=s1["std"],
            ),
            schemas.PeriodCompare(
                param_code=param_code,
                period_name="period2",
                mean=s2["mean"],
                max=s2["max"],
                min=s2["min"],
                std=s2["std"],
            ),
        ],
        delta_mean=delta,
    )


# ---------------------------------------------------------------------------
# 1. 基本统计  GET + POST
# ---------------------------------------------------------------------------
@router.get("/basic")
def basic_stats(
    param_code: str = Query(..., description="参数代号（必填）"),
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    start: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """基本统计：单参数 count / min / max / mean / variance / std / diff"""
    result = _do_basic_stats(db, param_code, satellite_id, start, end)
    return schemas.ok(result)


@router.post("/basic")
def basic_stats_post(
    body: schemas.StatisticsQuery,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """[POST] 基本统计：count / min / max / mean / variance / std / diff"""
    result = _do_basic_stats(db, body.param_code, body.satellite_id, body.start, body.end)
    return schemas.ok(result)


# ---------------------------------------------------------------------------
# 2. 趋势分析  GET + POST
# ---------------------------------------------------------------------------
@router.get("/trend")
def trend_analysis(
    param_code: str = Query(..., description="参数代号（必填）"),
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    start: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """趋势分析：最小二乘法线性回归斜率，判定上升 / 下降 / 平稳"""
    result = _do_trend_analysis(db, param_code, satellite_id, start, end)
    return schemas.ok(result)


@router.post("/trend")
def trend_analysis_post(
    body: schemas.StatisticsQuery,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """[POST] 趋势分析：附 change_percent / change_rate / direction"""
    tr = _do_trend_analysis(db, body.param_code, body.satellite_id, body.start, body.end)
    data = tr.model_dump()
    data["change_rate"] = round(data["change_percent"] / 100, 6)
    data["direction"] = data["trend"]
    return schemas.ok(data)


# ---------------------------------------------------------------------------
# 3. 异常检测  GET /anomalies + POST /anomaly
# ---------------------------------------------------------------------------
@router.get("/anomalies")
def anomalies(
    param_code: str = Query(..., description="参数代号（必填）"),
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    start: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    threshold_min: Optional[float] = Query(None, description="自定义下限，不传则使用参数配置"),
    threshold_max: Optional[float] = Query(None, description="自定义上限，不传则使用参数配置"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """异常检测：标记 value 超出 [threshold_min, threshold_max] 的越界点"""
    result = _do_anomalies(db, param_code, satellite_id, start, end, threshold_min, threshold_max)
    return schemas.ok(result)


@router.post("/anomaly")
def anomaly_post(
    body: schemas.StatisticsQuery = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """[POST] 异常检测：返回 { anomalies: [...] }"""
    items = _do_anomalies(
        db, body.param_code, body.satellite_id,
        body.start, body.end, body.threshold_min, body.threshold_max,
    )
    return schemas.ok({"anomalies": items})


# ---------------------------------------------------------------------------
# 4. 阶段对比  GET + POST
# ---------------------------------------------------------------------------
@router.get("/compare")
def period_compare(
    param_code: str = Query(..., description="参数代号（必填）"),
    satellite_id: Optional[int] = Query(None, description="卫星ID"),
    period1_start: Optional[str] = Query(None, alias="period1_start", description="阶段1起始时间"),
    period1_end: Optional[str] = Query(None, alias="period1_end", description="阶段1结束时间"),
    period2_start: Optional[str] = Query(None, alias="period2_start", description="阶段2起始时间"),
    period2_end: Optional[str] = Query(None, alias="period2_end", description="阶段2结束时间"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """阶段对比：两个时间段的数据统计对比，返回 delta_mean"""
    result = _do_compare(
        db, param_code, satellite_id,
        period1_start, period1_end,
        period2_start, period2_end,
    )
    return schemas.ok(result)


@router.post("/compare")
def period_compare_post(
    body: schemas.CompareQuery,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """[POST] 阶段对比：两个时间段的数据统计对比"""
    result = _do_compare(
        db, body.param_code, body.satellite_id,
        body.period1_start, body.period1_end,
        body.period2_start, body.period2_end,
    )
    return schemas.ok(result)
