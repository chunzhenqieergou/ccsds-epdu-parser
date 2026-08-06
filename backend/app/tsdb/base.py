"""
时序数据模型与抽象接口
=====================
Point 为与后端无关的轻量遥测点对象；TimeSeriesStore 定义统一读写接口。
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

logger: logging.Logger = logging.getLogger(__name__)


class Point:
    """遥测数据点（与后端无关的轻量对象，兼容 SQLAlchemy 行对象属性访问）。"""

    __slots__ = ("ts", "satellite_id", "channel_id", "param_code",
                 "raw_value", "value", "quality")

    def __init__(
        self,
        ts: datetime,
        satellite_id: int,
        channel_id: int,
        param_code: str,
        raw_value: int,
        value: float,
        quality: str = "GOOD",
    ) -> None:
        self.ts = ts
        self.satellite_id = satellite_id
        self.channel_id = channel_id
        self.param_code = param_code
        self.raw_value = raw_value
        self.value = value
        self.quality = quality

    @classmethod
    def from_dict(cls, d: dict) -> "Point":
        return cls(
            ts=d["ts"] if isinstance(d["ts"], datetime) else datetime.fromisoformat(d["ts"]),
            satellite_id=int(d.get("satellite_id", 0)),
            channel_id=int(d.get("channel_id", 0)),
            param_code=str(d["param_code"]),
            raw_value=int(d.get("raw_value", 0)),
            value=float(d.get("value", 0.0)),
            quality=str(d.get("quality", "GOOD")),
        )

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "satellite_id": self.satellite_id,
            "channel_id": self.channel_id,
            "param_code": self.param_code,
            "raw_value": self.raw_value,
            "value": self.value,
            "quality": self.quality,
        }

    def __repr__(self) -> str:
        return (
            f"Point(param={self.param_code}, ts={self.ts.isoformat()}, "
            f"value={self.value}, raw={self.raw_value})"
        )


class TimeSeriesStore(ABC):
    """时序存储统一接口（写 / 查 / 聚合）。"""

    backend: str = "base"

    # ---------------------------------------------------------------
    # 写
    # ---------------------------------------------------------------
    @abstractmethod
    def insert_points(self, points: list[dict]) -> None:
        """批量写入遥测点。

        Args:
            points: 字典列表，字段含 ts(datetime)/satellite_id/channel_id/
                    param_code/raw_value/value/quality
        """

    # ---------------------------------------------------------------
    # 查
    # ---------------------------------------------------------------
    @abstractmethod
    def query(
        self,
        *,
        satellite_id: Optional[int],
        param_codes: list[str],
        channel_ids: Optional[list[int]],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        page: int,
        page_size: int,
    ) -> tuple[int, list[Point]]:
        """分页查询，返回 (总数, 按时间升序的 Point 列表)。"""

    @abstractmethod
    def query_all(
        self,
        *,
        satellite_id: Optional[int],
        param_codes: list[str],
        channel_ids: Optional[list[int]],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> list[Point]:
        """全量查询（时间升序），供自动抽样降采样使用。"""

    @abstractmethod
    def latest(
        self,
        *,
        satellite_id: Optional[int],
        param_codes: list[str],
    ) -> list[Point]:
        """每个 param_code 的最新一条记录。"""

    @abstractmethod
    def values(
        self,
        *,
        param_code: str,
        satellite_id: Optional[int],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> list[float]:
        """查询某参数在时间窗内的工程值序列（仅 value）。"""

    @abstractmethod
    def values_with_ts(
        self,
        *,
        param_code: str,
        satellite_id: Optional[int],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> list[tuple[datetime, float]]:
        """查询某参数 (ts, value) 序列，按时间升序。"""

    # ---------------------------------------------------------------
    # 聚合
    # ---------------------------------------------------------------
    @abstractmethod
    def stats(
        self,
        *,
        param_code: str,
        satellite_id: Optional[int],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
    ) -> dict:
        """聚合统计：count/min/max/mean/variance/std/diff。"""

    @abstractmethod
    def health(self) -> bool:
        """后端连通性检查。"""
