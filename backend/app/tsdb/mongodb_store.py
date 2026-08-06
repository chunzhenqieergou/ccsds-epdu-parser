"""
MongoDB 时序存储实现（方案 B）
============================
利用 MongoDB 文档模型 + 复合索引 + 聚合管道实现时序存储：
  - 集合 telemetry_data，文档: {ts, satellite_id, channel_id, param_code,
    raw_value, value, quality}
  - 复合索引 (param_code, ts) 支撑按参数+时间查询
  - TTL 索引自动清理 N 天前数据（默认 90 天）
  - 聚合管道实现 MAX/MIN/AVG/STD 等统计
任何操作失败自动降级回退 MySQL（数据不丢、服务不崩）。
"""
import logging
import threading
from datetime import datetime
from typing import Optional

from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

from ..config import settings
from .base import Point, TimeSeriesStore

logger: logging.Logger = logging.getLogger(__name__)


class MongoDBTimeSeriesStore(TimeSeriesStore):
    """基于 MongoDB 的时序存储实现。"""

    backend: str = "mongodb"

    def __init__(self) -> None:
        self._client: MongoClient | None = None
        self._lock = threading.Lock()
        self._fallback: TimeSeriesStore | None = None
        self._degraded = False
        self._db_name = settings.MONGODB_DB
        self._coll_name = settings.MONGODB_COLLECTION

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def _get_client(self) -> MongoClient:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = MongoClient(
                        settings.MONGODB_URI,
                        serverSelectionTimeoutMS=3000,
                        connectTimeoutMS=3000,
                    )
                    self._ensure_indexes()
        return self._client

    def _ensure_indexes(self) -> None:
        coll = self._client[self._db_name][self._coll_name]
        # 按参数 + 时间的高效查询（方案 4.2 复合索引）
        coll.create_index([("param_code", ASCENDING), ("ts", ASCENDING)],
                          name="idx_param_ts")
        # TTL 自动清理（方案 4.2 TTL 索引，默认 90 天）；未启用时建普通 ts 索引
        ttl = settings.MONGODB_TTL_DAYS
        if ttl and ttl > 0:
            coll.create_index(
                [("ts", ASCENDING)],
                name="idx_ts_ttl",
                expireAfterSeconds=ttl * 24 * 3600,
            )
        else:
            coll.create_index([("ts", ASCENDING)], name="idx_ts")

    def _coll(self):
        client = self._get_client()
        return client[self._db_name][self._coll_name]

    @staticmethod
    def _naive(dt: Optional[datetime]) -> Optional[datetime]:
        """去时区（项目统一使用本地 naive 时间）"""
        if dt is not None and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    # ------------------------------------------------------------------
    # 降级回退
    # ------------------------------------------------------------------
    def _fallback_store(self) -> TimeSeriesStore:
        if self._fallback is None:
            from .mysql_store import MySQLTimeSeriesStore
            self._fallback = MySQLTimeSeriesStore()
        return self._fallback

    def _warn_degraded(self, op: str, exc: Exception) -> None:
        if not self._degraded:
            self._degraded = True
            logger.warning("MongoDB 时序后端操作 %s 失败(%s)，已降级回退 MySQL", op, exc)
        else:
            logger.debug("MongoDB 时序后端仍不可用: %s", exc)

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------
    def insert_points(self, points: list[dict]) -> None:
        if not points:
            return
        try:
            docs = []
            for pt in points:
                ts = pt["ts"]
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                docs.append({
                    "ts": ts,
                    "satellite_id": int(pt.get("satellite_id", 0)),
                    "channel_id": int(pt.get("channel_id", 0)),
                    "param_code": str(pt["param_code"]),
                    "raw_value": int(pt.get("raw_value", 0)),
                    "value": float(pt.get("value", 0.0)),
                    "quality": str(pt.get("quality", "GOOD")),
                })
            coll = self._coll()
            for i in range(0, len(docs), 500):
                coll.insert_many(docs[i:i + 500], ordered=False)
            if self._degraded:
                self._degraded = False
                logger.info("MongoDB 时序后端已恢复")
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("insert", exc)
            self._fallback_store().insert_points(points)

    # ------------------------------------------------------------------
    # 查
    # ------------------------------------------------------------------
    @staticmethod
    def _doc_to_point(doc: dict) -> Point:
        return Point(
            ts=doc["ts"] if isinstance(doc["ts"], datetime)
            else datetime.fromisoformat(str(doc["ts"])),
            satellite_id=int(doc.get("satellite_id", 0)),
            channel_id=int(doc.get("channel_id", 0)),
            param_code=str(doc["param_code"]),
            raw_value=int(doc.get("raw_value", 0)),
            value=float(doc.get("value", 0.0)),
            quality=str(doc.get("quality", "GOOD")),
        )

    def _filter(self, *, satellite_id, param_codes, channel_ids, start_dt, end_dt) -> dict:
        flt: dict = {}
        if satellite_id:
            flt["satellite_id"] = satellite_id
        if channel_ids:
            flt["channel_id"] = {"$in": channel_ids}
        if param_codes:
            flt["param_code"] = {"$in": param_codes}
        if start_dt or end_dt:
            ts_flt: dict = {}
            if start_dt:
                ts_flt["$gte"] = self._naive(start_dt)
            if end_dt:
                ts_flt["$lte"] = self._naive(end_dt)
            flt["ts"] = ts_flt
        return flt

    def query(self, *, satellite_id, param_codes, channel_ids, start_dt, end_dt,
              page, page_size) -> tuple[int, list[Point]]:
        try:
            coll = self._coll()
            flt = self._filter(satellite_id=satellite_id, param_codes=param_codes,
                               channel_ids=channel_ids, start_dt=start_dt, end_dt=end_dt)
            total = coll.count_documents(flt)
            cursor = coll.find(flt).sort("ts", ASCENDING) \
                .skip((page - 1) * page_size).limit(page_size)
            return total, [self._doc_to_point(d) for d in cursor]
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("query", exc)
            return self._fallback_store().query(
                satellite_id=satellite_id, param_codes=param_codes,
                channel_ids=channel_ids, start_dt=start_dt, end_dt=end_dt,
                page=page, page_size=page_size)

    def query_all(self, *, satellite_id, param_codes, channel_ids, start_dt, end_dt) -> list[Point]:
        try:
            coll = self._coll()
            flt = self._filter(satellite_id=satellite_id, param_codes=param_codes,
                               channel_ids=channel_ids, start_dt=start_dt, end_dt=end_dt)
            cursor = coll.find(flt).sort("ts", ASCENDING)
            return [self._doc_to_point(d) for d in cursor]
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("query_all", exc)
            return self._fallback_store().query_all(
                satellite_id=satellite_id, param_codes=param_codes,
                channel_ids=channel_ids, start_dt=start_dt, end_dt=end_dt)

    def latest(self, *, satellite_id, param_codes) -> list[Point]:
        try:
            coll = self._coll()
            match: dict = {}
            if satellite_id:
                match["satellite_id"] = satellite_id
            if param_codes:
                match["param_code"] = {"$in": param_codes}
            # 每个 param_code 取 ts 最大的一条
            pipeline = [
                {"$match": match},
                {"$sort": {"ts": -1}},
                {"$group": {
                    "_id": "$param_code",
                    "doc": {"$first": "$$ROOT"},
                }},
                {"$replaceRoot": {"newRoot": "$doc"}},
            ]
            cursor = coll.aggregate(pipeline)
            return [self._doc_to_point(d) for d in cursor]
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("latest", exc)
            return self._fallback_store().latest(
                satellite_id=satellite_id, param_codes=param_codes)

    def values(self, *, param_code, satellite_id, start_dt, end_dt) -> list[float]:
        try:
            coll = self._coll()
            flt: dict = {"param_code": param_code}
            if satellite_id:
                flt["satellite_id"] = satellite_id
            if start_dt or end_dt:
                ts_flt: dict = {}
                if start_dt:
                    ts_flt["$gte"] = self._naive(start_dt)
                if end_dt:
                    ts_flt["$lte"] = self._naive(end_dt)
                flt["ts"] = ts_flt
            return [float(d["value"]) for d in coll.find(flt, {"value": 1})]
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("values", exc)
            return self._fallback_store().values(
                param_code=param_code, satellite_id=satellite_id,
                start_dt=start_dt, end_dt=end_dt)

    def values_with_ts(self, *, param_code, satellite_id, start_dt, end_dt) -> list[tuple[datetime, float]]:
        try:
            coll = self._coll()
            flt: dict = {"param_code": param_code}
            if satellite_id:
                flt["satellite_id"] = satellite_id
            if start_dt or end_dt:
                ts_flt: dict = {}
                if start_dt:
                    ts_flt["$gte"] = self._naive(start_dt)
                if end_dt:
                    ts_flt["$lte"] = self._naive(end_dt)
                flt["ts"] = ts_flt
            cursor = coll.find(flt, {"ts": 1, "value": 1}).sort("ts", ASCENDING)
            return [
                (d["ts"] if isinstance(d["ts"], datetime)
                 else datetime.fromisoformat(str(d["ts"])), float(d["value"]))
                for d in cursor
            ]
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("values_with_ts", exc)
            return self._fallback_store().values_with_ts(
                param_code=param_code, satellite_id=satellite_id,
                start_dt=start_dt, end_dt=end_dt)

    # ------------------------------------------------------------------
    # 聚合（方案 4.2 聚合管道）
    # ------------------------------------------------------------------
    def stats(self, *, param_code, satellite_id, start_dt, end_dt) -> dict:
        try:
            coll = self._coll()
            match: dict = {"param_code": param_code}
            if satellite_id:
                match["satellite_id"] = satellite_id
            if start_dt or end_dt:
                ts_flt: dict = {}
                if start_dt:
                    ts_flt["$gte"] = self._naive(start_dt)
                if end_dt:
                    ts_flt["$lte"] = self._naive(end_dt)
                match["ts"] = ts_flt
            pipeline = [
                {"$match": match},
                {"$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "min": {"$min": "$value"},
                    "max": {"$max": "$value"},
                    "mean": {"$avg": "$value"},
                    "std": {"$stdDevPop": "$value"},
                }},
            ]
            docs = list(coll.aggregate(pipeline))
            if not docs or not docs[0].get("count"):
                return {"count": 0, "min": None, "max": None, "mean": None,
                        "variance": None, "std": None, "diff": None}
            g = docs[0]
            std = float(g.get("std") or 0.0)
            return {
                "count": int(g["count"]),
                "min": float(g["min"]),
                "max": float(g["max"]),
                "mean": float(g["mean"]),
                "variance": std * std,
                "std": std,
                "diff": float(g["max"] - g["min"]),
            }
        except (PyMongoError, Exception) as exc:  # noqa: BLE001
            self._warn_degraded("stats", exc)
            return self._fallback_store().stats(
                param_code=param_code, satellite_id=satellite_id,
                start_dt=start_dt, end_dt=end_dt)

    def health(self) -> bool:
        try:
            client = self._get_client()
            client.admin.command("ping")
            return True
        except Exception as exc:
            logger.warning("MongoDB 连通性检查失败: %s", exc)
            return False
