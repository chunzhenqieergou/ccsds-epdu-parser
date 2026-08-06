"""
卫星配置 CRUD API
=================
提供卫星的列表、创建、详情、更新、删除接口。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_current_user, require_operator, log_action, get_db

router = APIRouter()


@router.get("", include_in_schema=False)
@router.get("/")
def list_satellites(
    keyword: str | None = Query(None, description="按 code/name 模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """卫星列表，支持分页 + code/name 模糊搜索"""
    q = db.query(models.Satellite)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            or_(
                models.Satellite.code.like(kw),
                models.Satellite.name.like(kw),
            )
        )
    total = q.count()
    satellites = (
        q.order_by(models.Satellite.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for sat in satellites:
        sat_out = schemas.SatelliteOut.model_validate(sat)
        sat_out.param_count = len(sat.params)
        items.append(sat_out)

    return schemas.ok(
        schemas.PageResult(total=total, page=page, page_size=page_size, items=items)
    )


@router.post("", status_code=201, include_in_schema=False)
@router.post("/", status_code=201)
def create_satellite(
    body: schemas.SatelliteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """创建卫星（code 唯一校验）"""
    existing = db.query(models.Satellite).filter(
        models.Satellite.code == body.code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="卫星代号已存在")
    sat = models.Satellite(**body.model_dump())
    db.add(sat)
    db.commit()
    db.refresh(sat)
    log_action(
        db, current_user, "创建卫星",
        f"satellite:{sat.id}",
        f"创建卫星 {sat.name}({sat.code})",
        request,
    )
    sat_out = schemas.SatelliteOut.model_validate(sat)
    sat_out.param_count = 0
    return schemas.ok(sat_out)


@router.get("/{satellite_id}")
def get_satellite(
    satellite_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """卫星详情（含 param_count）"""
    sat = db.query(models.Satellite).filter(
        models.Satellite.id == satellite_id
    ).first()
    if not sat:
        raise HTTPException(status_code=404, detail="卫星不存在")
    sat_out = schemas.SatelliteOut.model_validate(sat)
    sat_out.param_count = len(sat.params)
    return schemas.ok(sat_out)


@router.put("/{satellite_id}")
def update_satellite(
    satellite_id: int,
    body: schemas.SatelliteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """更新卫星"""
    sat = db.query(models.Satellite).filter(
        models.Satellite.id == satellite_id
    ).first()
    if not sat:
        raise HTTPException(status_code=404, detail="卫星不存在")
    if body.code and body.code != sat.code:
        existing = db.query(models.Satellite).filter(
            models.Satellite.code == body.code
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="卫星代号已存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(sat, key, val)
    db.commit()
    db.refresh(sat)
    log_action(
        db, current_user, "更新卫星",
        f"satellite:{sat.id}",
        f"更新卫星 {sat.name}({sat.code})",
        request,
    )
    sat_out = schemas.SatelliteOut.model_validate(sat)
    sat_out.param_count = len(sat.params)
    return schemas.ok(sat_out)


@router.delete("/{satellite_id}")
def delete_satellite(
    satellite_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_operator),
    request: Request = None,
):
    """删除卫星（级联删除参数/通道）"""
    sat = db.query(models.Satellite).filter(
        models.Satellite.id == satellite_id
    ).first()
    if not sat:
        raise HTTPException(status_code=404, detail="卫星不存在")
    sat_name = sat.name
    sat_code = sat.code
    sat_id = sat.id
    db.delete(sat)
    db.commit()
    log_action(
        db, current_user, "删除卫星",
        f"satellite:{sat_id}",
        f"删除卫星 {sat_name}({sat_code})",
        request,
    )
    return schemas.ok(None, "已删除")
