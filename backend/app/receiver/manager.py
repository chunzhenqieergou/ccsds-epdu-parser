"""
数据接收与实时推送编排器
========================
ReceiverManager 管理模拟器与 Socket 服务器的生命周期，核心线程循环：
  周期调用 simulator 生成帧 → 解析参数点 → 批量写库（TelemetryData + TelemetryFrame）
  → SSE 实时推送 → 告警检查与入库。

对外接口：
  start()  — 启动后台流水线线程
  stop()   — 优雅停止
"""

import logging
import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import SessionLocal
from .simulator import simulator as _simulator, _load_channel_ids as _load_channels
from ..services.sse import sse_publish, bus as sse_bus
import asyncio

logger: logging.Logger = logging.getLogger(__name__)


class ReceiverManager:
    """数据接收与入库编排器。

    管理后台模拟线程，周期生成帧、写库、SSE 推送、告警检测。
    使用模块级单例 :data:`receiver_manager`。
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._lock: threading.Lock = threading.Lock()
        self._alarm_cache: set[tuple[int, str]] = set()  # (param_id, level) 用于告警去重

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动数据接收流水线（由 FastAPI lifespan 调用）。

        加载数据库参数配置，捕获当前 asyncio 事件循环供 SSE 跨线程发布，
        然后启动后台线程执行核心循环。
        """
        with self._lock:
            if self._running:
                return
            self._running = True

        # 捕获事件循环（start 在 lifespan 的 async 上下文中被调用）
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            sse_bus.set_loop(loop)
            logger.info("SSE 事件总线已绑定事件循环")
        except RuntimeError:
            logger.warning("无法获取运行中的事件循环，SSE 发布可能不可用")

        # 从数据库加载参数和通道配置
        db: Session = SessionLocal()
        try:
            _simulator.load_config(db)
            _load_channels(db)
            logger.info(
                "模拟器已加载 %d 个启用的遥测参数",
                len(_simulator.params),
            )
        finally:
            db.close()

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="receiver-manager",
        )
        self._thread.start()
        logger.info("数据接收流水线已启动")

    def stop(self) -> None:
        """停止数据接收流水线。"""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("数据接收流水线已停止")

    # ------------------------------------------------------------------
    # 核心循环
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """后台线程主循环。

        按 SIMULATOR_INTERVAL_MS 周期：
          1. 调用 simulate 生成参数点与协议帧
          2. 批量写入 TelemetryData 与 TelemetryFrame
          3. 逐点 SSE 推送 realtime_point
          4. 逐帧 SSE 推送 frame
          5. 告警阈值检测（写入 Alarm + SSE 推送 alarm）
        """
        interval_s: float = settings.SIMULATOR_INTERVAL_MS / 1000.0

        while self._running:
            cycle_start: float = time.time()

            try:
                db: Session = SessionLocal()
                try:
                    self._process_cycle(db)
                finally:
                    db.close()
            except Exception:
                logger.exception("数据接收周期处理异常")

            elapsed: float = time.time() - cycle_start
            sleep_s: float = max(0, interval_s - elapsed)
            # 休眠中使用短间隔检查停止标志
            while sleep_s > 0 and self._running:
                t: float = min(0.1, sleep_s)
                time.sleep(t)
                sleep_s -= t

    def _process_cycle(self, db: Session) -> None:
        """处理单个周期的数据生成、入库与推送。

        Args:
            db: SQLAlchemy 数据库会话（此方法内执行 commit）。
        """
        result: dict = _simulator.generate_cycle()
        ts: datetime = result["ts"]
        param_points: list[dict] = result["param_points"]
        frames: list[dict] = result["frames"]

        # ---- 1. 写入遥测数据 ----
        telemetry_records: list[models.TelemetryData] = []
        for pt in param_points:
            record: models.TelemetryData = models.TelemetryData(
                ts=ts,
                satellite_id=pt["satellite_id"],
                channel_id=pt.get("channel_id", 0),
                param_code=pt["param_code"],
                raw_value=pt.get("raw_value", 0),
                value=pt.get("value", 0.0),
                quality=pt.get("quality", "GOOD"),
            )
            telemetry_records.append(record)
            db.add(record)

        # ---- 2. 写入遥测原始帧 ----
        for fr in frames:
            frame_record: models.TelemetryFrame = models.TelemetryFrame(
                ts=ts,
                satellite_id=fr.get("satellite_id", 1),
                channel_id=fr.get("channel_id", 0),
                protocol_type=fr.get("protocol_type", "CCSDS"),
                apid=fr.get("apid", 0),
                raw_hex=fr.get("raw_hex", ""),
            )
            db.add(frame_record)

        # ---- 3. 一次提交 ----
        db.commit()

        # ---- 4. SSE 实时推送 ----
        ts_str: str = ts.isoformat()
        for pt in param_points:
            sse_publish("realtime_point", {
                "ts": ts_str,
                "satellite_id": pt["satellite_id"],
                "channel_id": pt.get("channel_id", 0),
                "param_code": pt["param_code"],
                "raw_value": pt.get("raw_value", 0),
                "value": pt.get("value", 0.0),
                "quality": pt.get("quality", "GOOD"),
            })

        for fr in frames:
            raw_hex: str = fr.get("raw_hex", "")
            sse_publish("frame", {
                "ts": ts_str,
                "satellite_id": fr.get("satellite_id", 1),
                "channel_id": fr.get("channel_id", 0),
                "protocol_type": fr.get("protocol_type", ""),
                "apid": fr.get("apid", 0),
                "raw_hex": raw_hex[:500],  # 截断避免超大帧撑爆 SSE
            })

        # ---- 5. 告警检测 ----
        self._detect_alarms(db, param_points, ts_str)

    # ------------------------------------------------------------------
    # 告警检测
    # ------------------------------------------------------------------

    def _detect_alarms(
        self, db: Session, param_points: list[dict], ts_str: str
    ) -> None:
        """阈值越界检测，写入 Alarm 表并通过 SSE 推送。

        Args:
            db: 数据库会话（会在此方法内执行额外 commit）。
            param_points: 本周期生成的参数点。
            ts_str: 时间戳字符串。
        """
        param_map: dict[str, models.TelemetryParam] = {
            p.param_code: p for p in _simulator.params
        }

        for pt in param_points:
            code: str = pt["param_code"]
            param: models.TelemetryParam | None = param_map.get(code)
            if param is None:
                continue

            value: float = pt.get("value", 0.0)
            threshold_min: float | None = param.threshold_min
            threshold_max: float | None = param.threshold_max

            alarm_triggered: bool = False
            level: str = "WARN"
            trigger_threshold: float | None = None
            direction: str = ""

            if threshold_max is not None and value > threshold_max:
                alarm_triggered = True
                trigger_threshold = threshold_max
                direction = "上限"
                level = "CRITICAL" if value > threshold_max * 1.2 else "WARN"
            elif threshold_min is not None and value < threshold_min:
                alarm_triggered = True
                trigger_threshold = threshold_min
                direction = "下限"
                level = "CRITICAL" if value < threshold_min * 0.8 else "WARN"

            if not alarm_triggered:
                continue

            # 去重：同一参数+级别在 1 分钟内只发一次（按 tick 简单去重）
            cache_key: tuple[int, str] = (param.id, level)
            if cache_key in self._alarm_cache:
                continue
            self._alarm_cache.add(cache_key)
            # 限制缓存大小
            if len(self._alarm_cache) > 200:
                self._alarm_cache.clear()

            alarm_record: models.Alarm = models.Alarm(
                param_id=param.id,
                alarm_type="threshold",
                threshold=trigger_threshold,
                actual_value=value,
                level=level,
                status=0,
                message=(
                    f"参数 {param.param_code}({param.name}) 越{direction}: "
                    f"当前={value}, 阈值={trigger_threshold}"
                ),
            )
            db.add(alarm_record)
            db.commit()

            sse_publish("alarm", {
                "ts": ts_str,
                "param_id": param.id,
                "param_code": param.param_code,
                "param_name": param.name,
                "value": value,
                "threshold": trigger_threshold,
                "level": level,
                "direction": direction,
            })


# 模块级单例 — main.py 的 lifespan 直接 import 使用
receiver_manager: ReceiverManager = ReceiverManager()
