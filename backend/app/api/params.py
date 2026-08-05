"""
遥测参数 CRUD API
=================
提供参数的列表、创建、详情、更新、删除、参数树、导入导出接口。
"""
import json
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from starlette.responses import StreamingResponse

from .. import models, schemas
from ..deps import get_current_user, require_operator, log_action, get_db

router = APIRouter()


def _param_out(param: models.TelemetryParam) -> schemas.TelemetryParamOut:
    """构建带 satellite_name 的输出"""
    out = schemas.TelemetryParamOut.model_validate(param)
    out.satellite_name = param.satellite.name if param.satellite else None
    return out


@router.get("", include_in_schema=False)
@router.get("/")
def list_params(
    satellite_id: int | None = Query(None, description="按卫星过滤"),
    subsystem: str | None = Query(None, description="按分系统过滤"),
    keyword: str | None = Query(None, description="按 param_code/name 模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """参数列表，支持卫星/分系统/关键字过滤和分页"""
    q = db.query(models.TelemetryParam).options(
        joinedload(models.TelemetryParam.satellite)
    )
    if satellite_id:
        q = q.filter(models.TelemetryParam.satellite_id == satellite_id)
    if subsystem:
        q = q.filter(models.TelemetryParam.subsystem == subsystem)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            or_(
                models.TelemetryParam.param_code.like(kw),
                models.TelemetryParam.name.like(kw),
            )
        )
    total = q.count()
    params = (
        q.order_by(models.TelemetryParam.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_param_out(p) for p in params]
    return schemas.ok(
        schemas.PageResult(total=total, page=page, page_size=page_size, items=items)
    )


@router.post("", status_code=201, include_in_schema=False)
@router.post("/", status_code=201)
def create_param(
    body: schemas.TelemetryParamCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """创建参数（同卫星下 param_code 唯一）"""
    sat = db.query(models.Satellite).filter(
        models.Satellite.id == body.satellite_id
    ).first()
    if not sat:
        raise HTTPException(status_code=404, detail="卫星不存在")
    existing = db.query(models.TelemetryParam).filter(
        models.TelemetryParam.satellite_id == body.satellite_id,
        models.TelemetryParam.param_code == body.param_code,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该卫星下参数代号已存在")
    param = models.TelemetryParam(**body.model_dump())
    db.add(param)
    db.commit()
    db.refresh(param)
    log_action(
        db, current_user, "创建参数",
        f"param:{param.id}",
        f"创建参数 {param.param_code}({param.name})",
        request,
    )
    return schemas.ok(_param_out(param))


@router.get("/tree")
def params_tree(
    satellite_id: int | None = Query(None, description="按卫星过滤"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """按分系统分组返回参数树，供前端参数树展示"""
    q = db.query(models.TelemetryParam).options(
        joinedload(models.TelemetryParam.satellite)
    )
    if satellite_id:
        q = q.filter(models.TelemetryParam.satellite_id == satellite_id)
    params = q.order_by(
        models.TelemetryParam.subsystem, models.TelemetryParam.order_no
    ).all()

    groups: dict[str, list[schemas.TelemetryParamOut]] = {}
    for p in params:
        groups.setdefault(p.subsystem, []).append(_param_out(p))

    result = [
        {"subsystem": k, "params": [item.model_dump() for item in v]}
        for k, v in groups.items()
    ]
    return schemas.ok(result)


@router.post("/import")
def import_params(
    body: list[dict],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """JSON 模板导入：对同卫星+param_code 已存在的跳过"""
    imported = 0
    skipped = 0
    errors: list[str] = []

    for i, item in enumerate(body):
        try:
            create_obj = schemas.TelemetryParamCreate(**item)
        except Exception as e:
            errors.append(f"第{i + 1}条数据校验失败: {e}")
            continue

        sat_id = create_obj.satellite_id
        param_code = create_obj.param_code

        existing = db.query(models.TelemetryParam).filter(
            models.TelemetryParam.satellite_id == sat_id,
            models.TelemetryParam.param_code == param_code,
        ).first()
        if existing:
            skipped += 1
            continue

        param = models.TelemetryParam(**create_obj.model_dump())
        db.add(param)
        imported += 1

    db.commit()
    log_action(
        db, current_user, "导入参数",
        None,
        f"导入 {imported} 条, 跳过 {skipped} 条",
        request,
    )
    return schemas.ok(
        schemas.ParamImportResult(
            imported=imported, skipped=skipped, errors=errors
        )
    )


@router.get("/export")
def export_params(
    satellite_id: int | None = Query(None, description="按卫星过滤"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """导出全部参数为 JSON 列表"""
    q = db.query(models.TelemetryParam).options(
        joinedload(models.TelemetryParam.satellite)
    )
    if satellite_id:
        q = q.filter(models.TelemetryParam.satellite_id == satellite_id)
    params = q.order_by(models.TelemetryParam.id).all()
    result = [_param_out(p).model_dump(mode="json") for p in params]
    return schemas.ok(result)


@router.post("/import/{satellite_id}")
def import_params_file(
    satellite_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    request: Request = None,
):
    """从上传的 JSON 文件导入参数"""
    try:
        content = file.file.read()
        items = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="\u6587\u4ef6\u89e3\u6790\u5931\u8d25\uff0c\u8bf7\u4e0a\u4f20\u6709\u6548\u7684 JSON \u6587\u4ef6")

    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="\u6587\u4ef6\u5185\u5bb9\u5e94\u4e3a JSON \u6570\u7ec4")

    imported = 0
    skipped = 0
    errors: list[str] = []

    for i, item in enumerate(items):
        try:
            item["satellite_id"] = satellite_id
            create_obj = schemas.TelemetryParamCreate(**item)
        except Exception as e:
            errors.append(f"\u7b2c{i + 1}\u6761\u6570\u636e\u6821\u9a8c\u5931\u8d25: {e}")
            continue

        existing = db.query(models.TelemetryParam).filter(
            models.TelemetryParam.satellite_id == satellite_id,
            models.TelemetryParam.param_code == create_obj.param_code,
        ).first()
        if existing:
            skipped += 1
            continue

        param = models.TelemetryParam(**create_obj.model_dump())
        db.add(param)
        imported += 1

    db.commit()
    log_action(
        db, current_user, "\u5bfc\u5165\u53c2\u6570",
        None,
        f"\u901a\u8fc7\u6587\u4ef6\u5bfc\u5165 {imported} \u6761, \u8df3\u8fc7 {skipped} \u6761",
        request,
    )
    return schemas.ok(
        schemas.ParamImportResult(
            imported=imported, skipped=skipped, errors=errors
        )
    )


@router.get("/export/{satellite_id}")
def export_params_file(
    satellite_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """导出卫星参数为 JSON 文件下载"""
    params = (
        db.query(models.TelemetryParam)
        .options(joinedload(models.TelemetryParam.satellite))
        .filter(models.TelemetryParam.satellite_id == satellite_id)
        .order_by(models.TelemetryParam.id)
        .all()
    )
    result = [_param_out(p).model_dump(mode="json") for p in params]
    json_str = json.dumps(result, ensure_ascii=False, default=str)
    return StreamingResponse(
        BytesIO(json_str.encode("utf-8")),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=params_{satellite_id}.json"
        },
    )


@router.get("/{param_id}")
def get_param(
    param_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """参数详情"""
    param = db.query(models.TelemetryParam).options(
        joinedload(models.TelemetryParam.satellite)
    ).filter(models.TelemetryParam.id == param_id).first()
    if not param:
        raise HTTPException(status_code=404, detail="参数不存在")
    return schemas.ok(_param_out(param))


@router.put("/{param_id}")
def update_param(
    param_id: int,
    body: schemas.TelemetryParamUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """更新参数"""
    param = db.query(models.TelemetryParam).filter(
        models.TelemetryParam.id == param_id
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="参数不存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(param, key, val)
    db.commit()
    db.refresh(param)
    log_action(
        db, current_user, "更新参数",
        f"param:{param.id}",
        f"更新参数 {param.param_code}({param.name})",
        request,
    )
    return schemas.ok(_param_out(param))


@router.delete("/{param_id}")
def delete_param(
    param_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """删除参数"""
    param = db.query(models.TelemetryParam).filter(
        models.TelemetryParam.id == param_id
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="参数不存在")
    param_code = param.param_code
    param_name = param.name
    pid = param.id
    db.delete(param)
    db.commit()
    log_action(
        db, current_user, "删除参数",
        f"param:{pid}",
        f"删除参数 {param_code}({param_name})",
        request,
    )
    return schemas.ok(None, "已删除")
