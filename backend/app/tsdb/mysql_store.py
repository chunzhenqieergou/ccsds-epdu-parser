"""
MySQL 时序存储实现（默认 / 回退后端）
===================================
复用原有 TelemetryData 表与 SQLAlchemy 查询逻辑，接口对齐 TimeSeriesStore。
"""
import math
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from .base import Point, TimeSeriesStore

logger: logging.Logger = logging.getLogger(__name__)


class MySQLTimeSeriesStore(TimeSeriesStore):
    """基于 MySQL TelemetryData 表的时序存储实现。"""

    backend: str = "mysql"

    @staticmethod
    def _naive(dt: Optional[datetime]) -> Optional[datetime]:
        """去时区（项目统一使用本地 naive 时间，避免 aware/naive 比较异常）"""
        if dt is not None and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    # ---------------------------------------------------------------
    # 写
    # ---------------------------------------------------------------
    def insert_points(self, points: list[dict]) -> None:
        if not points:
            return
        db: Session = SessionLocal()
        try:
            for pt in points:
                db.add(models.TelemetryData(
                    ts=pt["ts"],
                    satellite_id=pt.get("satellite_id", 0),
                    channel_id=pt.get("channel_id", 0),
                    param_code=pt["param_code"],
                    raw_value=pt.get("raw_value", 0),
                    value=pt.get("value", 0.0),
                    quality=pt.get("quality", "GOOD"),
                ))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ---------------------------------------------------------------
    # 查
    # ---------------------------------------------------------------
    def _build_query(self, db: Session, *, satellite_id, param_codes, channel_ids,
                     start_dt, end_dt):
        q = db.query(models.TelemetryData)
        if satellite_id:
            q = q.filter(models.TelemetryData.satellite_id == satellite_id)
        if channel_ids:
            q = q.filter(models.TelemetryData.channel_id.in_(channel_ids))
        if param_codes:
            q = q.filter(models.TelemetryData.param_code.in_(param_codes))
        if start_dt:
            q = q.filter(models.TelemetryData.ts >= self._naive(start_dt))
        if end_dt:
            q = q.filter(models.TelemetryData.ts <= self._naive(end_dt))
        return q

    @staticmethod
    def _to_point(row) -> Point:
        return Point(
            ts=row.ts,
            satellite_id=row.satellite_id,
            channel_id=row.channel_id,
            param_code=row.param_code,
            raw_value=row.raw_value,
            value=row.value,
            quality=row.quality,
        )

    def query(self, *, satellite_id, param_codes, channel_ids, start_dt, end_dt,
              page, page_size) -> tuple[int, list[Point]]:
        db: Session = SessionLocal()
        try:
            q = self._build_query(db, satellite_id=satellite_id, param_codes=param_codes,
                                  channel_ids=channel_ids, start_dt=start_dt, end_dt=end_dt)
            total = q.count()
            rows = q.order_by(models.TelemetryData.ts.asc()) \
                    .offset((page - 1) * page_size) \
                    .limit(page_size) \
                    .all()
            return total, [self._to_point(r) for r in rows]
        finally:
            db.close()

    def query_all(self, *, satellite_id, param_codes, channel_ids, start_dt, end_dt) -> list[Point]:
        db: Session = SessionLocal()
        try:
            q = self._build_query(db, satellite_id=satellite_id, param_codes=param_codes,
                                  channel_ids=channel_ids, start_dt=start_dt, end_dt=end_dt)
            rows = q.order_by(models.TelemetryData.ts.asc()).all()
            return [self._to_point(r) for r in rows]
        finally:
            db.close()

    def latest(self, *, satellite_id, param_codes) -> list[Point]:
        db: Session = SessionLocal()
        try:
            subq = db.query(
                models.TelemetryData.param_code,
                func.max(models.TelemetryData.ts).label("max_ts"),
            )
            if satellite_id:
                subq = subq.filter(models.TelemetryData.satellite_id == satellite_id)
            if param_codes:
                subq = subq.filter(models.TelemetryData.param_code.in_(param_codes))
            subq = subq.group_by(models.TelemetryData.param_code).subquery()

            rows = db.query(models.TelemetryData).join(
                subq,
                and_(
                    models.TelemetryData.param_code == subq.c.param_code,
                    models.TelemetryData.ts == subq.c.max_ts,
                ),
            ).all()
            return [self._to_point(r) for r in rows]
        finally:
            db.close()

    def values(self, *, param_code, satellite_id, start_dt, end_dt) -> list[float]:
        db: Session = SessionLocal()
        try:
            q = db.query(models.TelemetryData.value).filter(
                models.TelemetryData.param_code == param_code
            )
            if satellite_id:
                q = q.filter(models.TelemetryData.satellite_id == satellite_id)
            if start_dt:
                q = q.filter(models.TelemetryData.ts >= self._naive(start_dt))
            if end_dt:
                q = q.filter(models.TelemetryData.ts <= self._naive(end_dt))
            return [row[0] for row in q.all()]
        finally:
            db.close()

    def values_with_ts(self, *, param_code, satellite_id, start_dt, end_dt) -> list[tuple[datetime, float]]:
        db: Session = SessionLocal()
        try:
            q = db.query(models.TelemetryData.ts, models.TelemetryData.value).filter(
                models.TelemetryData.param_code == param_code
            )
            if satellite_id:
                q = q.filter(models.TelemetryData.satellite_id == satellite_id)
            if start_dt:
                q = q.filter(models.TelemetryData.ts >= self._naive(start_dt))
            if end_dt:
                q = q.filter(models.TelemetryData.ts <= self._naive(end_dt))
            return q.order_by(models.TelemetryData.ts.asc()).all()
        finally:
            db.close()

    # ---------------------------------------------------------------
    # 聚合
    # ---------------------------------------------------------------
    def stats(self, *, param_code, satellite_id, start_dt, end_dt) -> dict:
        db: Session = SessionLocal()
        try:
            q = db.query(
                func.count(models.TelemetryData.value),
                func.min(models.TelemetryData.value),
                func.max(models.TelemetryData.value),
                func.avg(models.TelemetryData.value),
                func.stddev_pop(models.TelemetryData.value),
            ).filter(models.TelemetryData.param_code == param_code)
            if satellite_id:
                q = q.filter(models.TelemetryData.satellite_id == satellite_id)
            if start_dt:
                q = q.filter(models.TelemetryData.ts >= self._naive(start_dt))
            if end_dt:
                q = q.filter(models.TelemetryData.ts <= self._naive(end_dt))
            count, min_v, max_v, avg_v, std_v = q.first()
            if not count:
                return {"count": 0, "min": None, "max": None, "mean": None,
                        "variance": None, "std": None, "diff": None}
            variance = (std_v or 0.0) ** 2
            return {
                "count": int(count),
                "min": float(min_v),
                "max": float(max_v),
                "mean": float(avg_v),
                "variance": float(variance),
                "std": float(std_v or 0.0),
                "diff": float(max_v - min_v),
            }
        finally:
            db.close()

    def health(self) -> bool:
        try:
            db: Session = SessionLocal()
            try:
                db.execute(func.count(models.TelemetryData.id).select())
                return True
            finally:
                db.close()
        except Exception:
            logger.exception("MySQL 时序后端连通性检查失败")
            return False
