"""
数据导出模块
============
按时间范围、参数代号、通道筛选，导出 CSV/Excel/JSON/TXT 四种格式。
文件流式下载，使用 pandas 生成，兼容 Excel utf-8-sig 编码。
同时提供 GET（Query 参数）与 POST（JSON Body）两种调用方式。
"""
from datetime import datetime
from io import BytesIO
import json

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, get_db, log_action

router = APIRouter()

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _parse_csv_int_list(value: str | None) -> list[int] | None:
    if not value:
        return None
    items = [s.strip() for s in value.split(",") if s.strip()]
    if not items:
        return None
    return [int(s) for s in items]


def _parse_dt(value: str) -> datetime:
    """解析 ISO 8601 时间字符串（兼容 Z 后缀）"""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _dt_filename(dt: datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# 核心查询
# ---------------------------------------------------------------------------

COLUMNS = ["ts", "param_code", "raw_value", "value", "quality", "satellite_id", "channel_id"]


def export_data(
    start: datetime,
    end: datetime,
    param_codes: list[str],
    channel_ids: list[int] | None,
    db: Session,
) -> pd.DataFrame:
    """查询 TelemetryData 行，按 ts 升序返回 DataFrame"""
    q = db.query(models.TelemetryData).filter(
        models.TelemetryData.ts >= start,
        models.TelemetryData.ts <= end,
        models.TelemetryData.param_code.in_(param_codes),
    )
    if channel_ids:
        q = q.filter(models.TelemetryData.channel_id.in_(channel_ids))
    q = q.order_by(models.TelemetryData.ts.asc())
    rows = q.all()

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    data = [
        {
            "ts": r.ts,
            "param_code": r.param_code,
            "raw_value": r.raw_value,
            "value": r.value,
            "quality": r.quality,
            "satellite_id": r.satellite_id,
            "channel_id": r.channel_id,
        }
        for r in rows
    ]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# 导出响应构建（GET / POST 共用）
# ---------------------------------------------------------------------------
def _export_csv_response(
    start: str, end: str, param_codes: list[str], channel_ids: list[int] | None,
    db: Session, current_user: models.User, request: Request | None,
) -> StreamingResponse:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    chs = channel_ids

    df = export_data(start_dt, end_dt, param_codes, chs, db)

    buf = BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    buf.seek(0)

    filename = f"telemetry_{_dt_filename(start_dt)}_{_dt_filename(end_dt)}.csv"
    log_action(db, current_user, "export", target="fmt:csv", detail=",".join(param_codes), request=request)

    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_excel_response(
    start: str, end: str, param_codes: list[str], channel_ids: list[int] | None,
    db: Session, current_user: models.User, request: Request | None,
) -> StreamingResponse:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    chs = channel_ids

    df = export_data(start_dt, end_dt, param_codes, chs, db)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="遥测数据", index=False)

        if param_codes:
            params = (
                db.query(models.TelemetryParam)
                .filter(models.TelemetryParam.param_code.in_(param_codes))
                .all()
            )
            if params:
                meta = pd.DataFrame(
                    [
                        {
                            "param_code": p.param_code,
                            "name": p.name,
                            "unit": p.unit,
                            "subsystem": p.subsystem,
                            "description": p.description,
                        }
                        for p in params
                    ]
                )
                meta.to_excel(writer, sheet_name="参数元数据", index=False)

    buf.seek(0)

    filename = f"telemetry_{_dt_filename(start_dt)}_{_dt_filename(end_dt)}.xlsx"
    log_action(db, current_user, "export", target="fmt:xlsx", detail=",".join(param_codes), request=request)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_json_response(
    start: str, end: str, param_codes: list[str], channel_ids: list[int] | None,
    db: Session, current_user: models.User, request: Request | None,
) -> StreamingResponse:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    chs = channel_ids

    df = export_data(start_dt, end_dt, param_codes, chs, db)

    if not df.empty:
        df = df.copy()
        df["ts"] = df["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    records = df.to_dict(orient="records")
    content = json.dumps(records, ensure_ascii=False, indent=2)

    filename = f"telemetry_{_dt_filename(start_dt)}_{_dt_filename(end_dt)}.json"
    log_action(db, current_user, "export", target="fmt:json", detail=",".join(param_codes), request=request)

    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_txt_response(
    start: str, end: str, param_codes: list[str], channel_ids: list[int] | None,
    db: Session, current_user: models.User, request: Request | None,
) -> StreamingResponse:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    chs = channel_ids

    df = export_data(start_dt, end_dt, param_codes, chs, db)

    lines: list[str] = []
    if not df.empty:
        for _, row in df.iterrows():
            ts_str = row["ts"].strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"{ts_str},{row['param_code']},{row['value']},{row['quality']}\n")
    content = "".join(lines)

    filename = f"telemetry_{_dt_filename(start_dt)}_{_dt_filename(end_dt)}.txt"
    log_action(db, current_user, "export", target="fmt:txt", detail=",".join(param_codes), request=request)

    return StreamingResponse(
        iter([content]),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 导出参数解析（GET 从 Query 提取，POST 从 Body 提取）
# ---------------------------------------------------------------------------
def _parse_export_get_params(
    start: str, end: str, param_codes: str, channel_ids: str | None,
) -> tuple:
    codes = _parse_csv_list(param_codes)
    chs = _parse_csv_int_list(channel_ids)
    return start, end, codes, chs


def _parse_export_post_params(body: schemas.ExportRequest) -> tuple:
    return body.start, body.end, body.param_codes, body.channel_ids


# ---------------------------------------------------------------------------
# CSV 导出  GET + POST
# ---------------------------------------------------------------------------

@router.get("/csv")
def export_csv(
    start: str = Query(..., description="开始时间 (ISO 8601)"),
    end: str = Query(..., description="结束时间 (ISO 8601)"),
    param_codes: str = Query(..., description="参数代号，逗号分隔"),
    channel_ids: str | None = Query(None, description="通道ID，逗号分隔（可选）"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """导出 CSV 文本（utf-8-sig，Excel 兼容）"""
    start_s, end_s, codes, chs = _parse_export_get_params(start, end, param_codes, channel_ids)
    return _export_csv_response(start_s, end_s, codes, chs, db, current_user, request)


@router.post("/csv")
def export_csv_post(
    body: schemas.ExportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """[POST] 导出 CSV 文本（utf-8-sig，Excel 兼容）"""
    start_s, end_s, codes, chs = _parse_export_post_params(body)
    return _export_csv_response(start_s, end_s, codes, chs, db, current_user, request)


# ---------------------------------------------------------------------------
# Excel 导出  GET + POST
# ---------------------------------------------------------------------------

@router.get("/excel")
def export_excel(
    start: str = Query(..., description="开始时间 (ISO 8601)"),
    end: str = Query(..., description="结束时间 (ISO 8601)"),
    param_codes: str = Query(..., description="参数代号，逗号分隔"),
    channel_ids: str | None = Query(None, description="通道ID，逗号分隔（可选）"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """导出 Excel 多 Sheet（遥测数据 + 参数元数据）"""
    start_s, end_s, codes, chs = _parse_export_get_params(start, end, param_codes, channel_ids)
    return _export_excel_response(start_s, end_s, codes, chs, db, current_user, request)


@router.post("/excel")
def export_excel_post(
    body: schemas.ExportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """[POST] 导出 Excel 多 Sheet（遥测数据 + 参数元数据）"""
    start_s, end_s, codes, chs = _parse_export_post_params(body)
    return _export_excel_response(start_s, end_s, codes, chs, db, current_user, request)


# ---------------------------------------------------------------------------
# JSON 导出  GET + POST
# ---------------------------------------------------------------------------

@router.get("/json")
def export_json(
    start: str = Query(..., description="开始时间 (ISO 8601)"),
    end: str = Query(..., description="结束时间 (ISO 8601)"),
    param_codes: str = Query(..., description="参数代号，逗号分隔"),
    channel_ids: str | None = Query(None, description="通道ID，逗号分隔（可选）"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """导出 JSON 列表文件"""
    start_s, end_s, codes, chs = _parse_export_get_params(start, end, param_codes, channel_ids)
    return _export_json_response(start_s, end_s, codes, chs, db, current_user, request)


@router.post("/json")
def export_json_post(
    body: schemas.ExportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """[POST] 导出 JSON 列表文件"""
    start_s, end_s, codes, chs = _parse_export_post_params(body)
    return _export_json_response(start_s, end_s, codes, chs, db, current_user, request)


# ---------------------------------------------------------------------------
# TXT 导出  GET + POST
# ---------------------------------------------------------------------------

@router.get("/txt")
def export_txt(
    start: str = Query(..., description="开始时间 (ISO 8601)"),
    end: str = Query(..., description="结束时间 (ISO 8601)"),
    param_codes: str = Query(..., description="参数代号，逗号分隔"),
    channel_ids: str | None = Query(None, description="通道ID，逗号分隔（可选）"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """导出固定格式文本（每行: YYYY-MM-DD HH:MM:SS,param_code,value,quality）"""
    start_s, end_s, codes, chs = _parse_export_get_params(start, end, param_codes, channel_ids)
    return _export_txt_response(start_s, end_s, codes, chs, db, current_user, request)


@router.post("/txt")
def export_txt_post(
    body: schemas.ExportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """[POST] 导出固定格式文本（每行: YYYY-MM-DD HH:MM:SS,param_code,value,quality）"""
    start_s, end_s, codes, chs = _parse_export_post_params(body)
    return _export_txt_response(start_s, end_s, codes, chs, db, current_user, request)


# ---------------------------------------------------------------------------
# Telemetry 通用导出  POST（对齐前端 telemetryApi.export.telemetry）
# ---------------------------------------------------------------------------
@router.post("/telemetry")
def export_telemetry_post(
    body: schemas.ExportRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """[POST] 通用遥测导出（复用 CSV 格式，字段与 /csv 一致）"""
    start_s, end_s, codes, chs = _parse_export_post_params(body)
    return _export_csv_response(start_s, end_s, codes, chs, db, current_user, request)
