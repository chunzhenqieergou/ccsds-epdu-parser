"""
数据接收与实时推送编排器
========================
ReceiverManager 管理两条数据链路：
  1. 模拟器链路（SIMULATOR_ENABLED）：周期生成帧 → 参数点 → 共享 ingest
  2. 真实接收链路（RECEIVER_ENABLED）：TCP/UDP 收到真实帧 → 协议解析 → 参数映射 → 共享 ingest

共享 ingest 统一做：时序入库(tsdb) + 原始帧入库(MySQL) + SSE 实时推送 + 告警检测。

对外接口：
  start()  — 按配置启动流水线线程（模拟器 / 真实接收）
  stop()   — 优雅停止
"""
import asyncio
import logging
import queue
import struct
import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import SessionLocal
from ..tsdb import get_tsdb_store
from ..protocols import ccsds, rs422
from ..protocols import m1553b as m1553b_mod
from ..services.sse import sse_publish, bus as sse_bus
from .simulator import simulator as _simulator, _load_channel_ids as _load_channels
from .server import real_receiver, channel_id_for_protocol, CCSDS_FRAME_LEN

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 帧 → 参数点解析（真实数据接收）
# ---------------------------------------------------------------------------
def _protocol_param_groups(params: list) -> dict:
    """把参数按模拟器同款策略均分到四类协议（保证收发对称）。"""
    n: int = len(params)
    q: int = max(1, n // 4) if n > 0 else 1
    return {
        "CCSDS": params[0:q],
        "1553B": params[q:q * 2],
        "CAN": params[q * 2:q * 3],
        "RS422": params[q * 3:],
    }


def _map_raws_to_params(
    raws: list, params: list, ts: datetime, channel_id: int,
) -> list[dict]:
    """原始字段值按序映射到参数点（raw → 工程值按 scale/offset 换算）。"""
    satellite_id: int = params[0].satellite_id if params else 1
    points: list[dict] = []
    for raw, p in zip(raws, params):
        value: float = p.offset + raw * p.scale
        points.append({
            "ts": ts,
            "satellite_id": satellite_id,
            "channel_id": channel_id,
            "param_code": p.param_code,
            "raw_value": int(raw),
            "value": round(value, p.precision),
            "quality": "GOOD",
        })
    return points


def parse_real_frame(
    protocol_type: str, data: bytes, params_by_proto: dict,
) -> tuple[list[dict], dict | None]:
    """把真实接收的帧解析为 (param_points, frame_info)。

    frame_info: {protocol_type, raw_hex, apid, channel_id, satellite_id}，
                解析失败返回 None。
    """
    ts: datetime = datetime.now()
    ch_id: int = channel_id_for_protocol(protocol_type)
    params: list = params_by_proto.get(protocol_type, [])
    raw_hex: str = data.hex().upper()

    if protocol_type == "CCSDS":
        if len(data) < CCSDS_FRAME_LEN:
            return [], None
        cadu = ccsds.parse_cadu_frame(data)
        if not cadu.get("ASM_valid"):
            return [], None
        zone: bytes = cadu.get("MPDU_data_zone", b"")
        ptr: int = cadu.get("first_header_pointer", 0)
        if len(zone) < ptr + 6:
            return [], None
        hdr = ccsds.parse_epdu_header(zone[ptr:ptr + 6])
        data_field: bytes = zone[ptr + 6:ptr + 6 + hdr.get("data_field_length", 0)]
        telemetry: bytes = data_field[:-2]  # 去掉 CRC
        apid: int = hdr.get("APID", 0)
        if len(telemetry) < 16:
            return [], {
                "protocol_type": protocol_type, "raw_hex": raw_hex,
                "apid": apid, "channel_id": ch_id,
                "satellite_id": params[0].satellite_id if params else 1,
            }
        # 姿态遥测布局: 4×int16 四元数 + 3×int16 角速度 + mode + act
        raws = struct.unpack(">hhhhhhhBB", telemetry[:16])
        points = _map_raws_to_params(raws, params, ts, ch_id)
        return points, {
            "protocol_type": protocol_type, "raw_hex": raw_hex,
            "apid": apid, "channel_id": ch_id,
            "satellite_id": params[0].satellite_id if params else 1,
        }

    if protocol_type == "1553B":
        if len(data) < 6:
            return [], None
        data_words: list[int] = [
            struct.unpack(">H", data[i:i + 2])[0]
            for i in range(2, len(data) - len(data) % 2, 2)
        ]
        points = _map_raws_to_params(data_words, params, ts, ch_id)
        return points, {
            "protocol_type": protocol_type, "raw_hex": raw_hex,
            "apid": 0, "channel_id": ch_id,
            "satellite_id": params[0].satellite_id if params else 1,
        }

    if protocol_type == "CAN":
        if len(data) < 12:
            return [], None
        arb_id: int = struct.unpack(">H", data[0:2])[0]
        dlc: int = data[2]
        data_bytes: bytes = data[4:4 + dlc]
        points = _map_raws_to_params(list(data_bytes), params, ts, ch_id)
        return points, {
            "protocol_type": protocol_type, "raw_hex": raw_hex,
            "apid": arb_id, "channel_id": ch_id,
            "satellite_id": params[0].satellite_id if params else 1,
        }

    if protocol_type == "RS422":
        parsed = rs422.parse_frame(data)
        if parsed is None or not parsed.get("crc_ok", False):
            return [], None
        values: list[float] = parsed.get("params", [])
        sat_id: int = parsed.get("satellite_id", 1)
        points: list[dict] = []
        for v, p in zip(values, params):
            points.append({
                "ts": ts,
                "satellite_id": sat_id,
                "channel_id": ch_id,
                "param_code": p.param_code,
                "raw_value": 0,
                "value": round(v, p.precision),
                "quality": "GOOD",
            })
        return points, {
            "protocol_type": protocol_type, "raw_hex": raw_hex,
            "apid": 0, "channel_id": ch_id,
            "satellite_id": sat_id,
        }

    return [], None


class ReceiverManager:
    """数据接收与入库编排器。

    管理模拟器线程与真实接收线程，统一走共享 ingest。
    使用模块级单例 :data:`receiver_manager`。
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._real_thread: threading.Thread | None = None
        self._lock: threading.Lock = threading.Lock()
        self._alarm_cache: set[tuple[int, str]] = set()  # (param_id, level) 告警去重
        self._param_map: dict[str, models.TelemetryParam] = {}
        self._params_by_proto: dict[str, list[models.TelemetryParam]] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def start(self) -> None:
        """按配置启动数据接收流水线（由 FastAPI lifespan 调用）。"""
        with self._lock:
            if self._running:
                return
            self._running = True

        # 捕获事件循环供 SSE 跨线程发布
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
            sse_bus.set_loop(loop)
            logger.info("SSE 事件总线已绑定事件循环")
        except RuntimeError:
            logger.warning("无法获取运行中的事件循环，SSE 发布可能不可用")

        # 加载参数与通道配置
        db: Session = SessionLocal()
        try:
            _simulator.load_config(db)
            _load_channels(db)
            self._param_map = {p.param_code: p for p in _simulator.params}
            self._params_by_proto = _protocol_param_groups(_simulator.params)
            logger.info("已加载 %d 个启用的遥测参数", len(_simulator.params))
        finally:
            db.close()

        # 模拟器链路
        if settings.SIMULATOR_ENABLED:
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True, name="receiver-manager"
            )
            self._thread.start()
            logger.info("模拟器数据流水线已启动")

        # 真实数据接收链路
        if settings.RECEIVER_ENABLED:
            real_receiver.start()
            self._real_thread = threading.Thread(
                target=self._real_loop, daemon=True, name="real-frame-ingest"
            )
            self._real_thread.start()
            logger.info("真实数据接收流水线已启动")

    def stop(self) -> None:
        """停止全部接收链路。"""
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if settings.RECEIVER_ENABLED:
            real_receiver.stop()
        if self._real_thread is not None:
            self._real_thread.join(timeout=5.0)
            self._real_thread = None
        logger.info("数据接收流水线已停止")

    # ------------------------------------------------------------------
    # 模拟器主循环
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        interval_s: float = settings.SIMULATOR_INTERVAL_MS / 1000.0

        while self._running:
            cycle_start: float = time.time()
            try:
                self._process_cycle()
            except Exception:
                logger.exception("模拟器周期处理异常")

            elapsed: float = time.time() - cycle_start
            sleep_s: float = max(0, interval_s - elapsed)
            while sleep_s > 0 and self._running:
                t: float = min(0.1, sleep_s)
                time.sleep(t)
                sleep_s -= t

    def _process_cycle(self) -> None:
        """模拟器单周期：生成 → 共享 ingest。"""
        result: dict = _simulator.generate_cycle()
        self._ingest(result["ts"], result["param_points"], result["frames"])

    # ------------------------------------------------------------------
    # 真实数据接收消费循环
    # ------------------------------------------------------------------
    def _real_loop(self) -> None:
        """消费真实帧队列：协议解析 → 参数映射 → 共享 ingest。"""
        while self._running:
            try:
                proto, data, _ch = real_receiver.frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception:
                logger.exception("真实帧队列读取异常")
                continue
            try:
                points, frame_info = parse_real_frame(proto, data, self._params_by_proto)
                if frame_info is None and not points:
                    continue
                frames: list[dict] = [frame_info] if frame_info else []
                ts: datetime = datetime.now()
                self._ingest(ts, points, frames)
            except Exception:
                logger.exception("真实帧处理异常")

    # ------------------------------------------------------------------
    # 共享下游：入库 + SSE + 告警
    # ------------------------------------------------------------------
    def _ingest(
        self, ts: datetime, param_points: list[dict], frames: list[dict],
    ) -> None:
        """统一数据落地：时序库 + 原始帧 + SSE 推送 + 告警检测。"""
        # 1. 遥测点写入时序存储层（MongoDB / MySQL 回退）
        tsdb = get_tsdb_store()
        tsdb_points: list[dict] = [{**pt, "ts": ts} for pt in param_points]
        if tsdb_points:
            tsdb.insert_points(tsdb_points)

        # 2. 原始帧写入 MySQL
        if frames:
            db: Session = SessionLocal()
            try:
                for fr in frames:
                    db.add(models.TelemetryFrame(
                        ts=ts,
                        satellite_id=fr.get("satellite_id", 1),
                        channel_id=fr.get("channel_id", 0),
                        protocol_type=fr.get("protocol_type", ""),
                        apid=fr.get("apid", 0),
                        raw_hex=fr.get("raw_hex", ""),
                    ))
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        # 3. SSE 实时推送
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
                "raw_hex": raw_hex[:500],
            })

        # 4. 告警检测
        if param_points:
            self._detect_alarms(param_points, ts_str)

    # ------------------------------------------------------------------
    # 告警检测
    # ------------------------------------------------------------------
    def _detect_alarms(self, param_points: list[dict], ts_str: str) -> None:
        """阈值越界检测，写入 Alarm 表并通过 SSE 推送。"""
        db: Session = SessionLocal()
        try:
            for pt in param_points:
                code: str = pt["param_code"]
                param: models.TelemetryParam | None = self._param_map.get(code)
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

                cache_key: tuple[int, str] = (param.id, level)
                if cache_key in self._alarm_cache:
                    continue
                self._alarm_cache.add(cache_key)
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
        finally:
            db.close()


# 模块级单例 — main.py 的 lifespan 直接 import 使用
receiver_manager: ReceiverManager = ReceiverManager()
