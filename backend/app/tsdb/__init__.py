"""
时序数据存储层（tsdb）
====================
抽象时序数据访问接口，支持两种后端：
  - MongoDB  : 专业文档型时序存储（方案 B，TTL/聚合管道）
  - MySQL    : 回退/默认后端（兼容原有 TelemetryData 表）

设计目标：读写路径统一走本层，API 层不感知后端差异。
"""
from .base import Point, TimeSeriesStore
from .factory import get_tsdb_store

__all__ = ["Point", "TimeSeriesStore", "get_tsdb_store"]
