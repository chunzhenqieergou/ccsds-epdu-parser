"""
数据模拟器
=========
读取数据库中的遥测参数配置，按时间序列生成模拟值（正弦+谐波），
并为四类协议（CCSDS、1553B、CAN、RS422）各构造至少一帧代表性帧。
确保「生成→解析→入库」闭环一致。

每个周期返回：
  - param_points: 所有启用参数的 (raw_value, value) 列表（用于 TelemetryData 入库）
  - frames: 四类协议帧的 raw_hex、protocol 等（用于 TelemetryFrame 入库）
"""

import math
import struct
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from ..protocols import ccsds, rs422
from ..protocols import m1553b as m1553b_mod


def _sim_value(tick: int, idx: int, amplitude: float, offset: float) -> float:
    """生成正弦+谐波模拟值（用于帧构建和参数点生成）。

    Args:
        tick: 周期序号。
        idx: 信号索引（用于区分不同信号的相位）。
        amplitude: 振幅。
        offset: 偏置。

    Returns:
        float: [-amplitude+offset, +amplitude+offset] 区间的模拟值。
    """
    freq: float = 0.02 + idx * 0.007
    phase: float = tick * freq
    harmonic: float = math.sin(phase * 0.31) * 0.2
    return math.sin(phase) * amplitude * 0.8 + harmonic * amplitude + offset


def _eng_to_raw(eng_value: float, param: models.TelemetryParam) -> int:
    """将工程值按参数定义的 scale/offset 逆换算为源码整型值。

    Args:
        eng_value: 工程值。
        param: 遥测参数定义。

    Returns:
        int: 源码整型值（裁剪到 raw_bits 位宽范围）。
    """
    if param.scale and param.scale != 0:
        raw: float = (eng_value - param.offset) / param.scale
    else:
        raw = eng_value - param.offset
    raw_int: int = int(round(raw))
    max_val: int = (1 << param.raw_bits) - 1
    if max_val > 0:
        raw_int = max(0, min(raw_int, max_val))
    return raw_int


# ---------------------------------------------------------------------------
# 各协议帧构建
# ---------------------------------------------------------------------------

def _build_ccsds_frame(tick: int, params: list[models.TelemetryParam]) -> dict[str, Any]:
    """构建 CCSDS CADU 帧（256 字节），嵌入姿态控制 EPDU 遥测包。

    Args:
        tick: 周期序号。
        params: 分配到此帧的参数列表（参数个数影响信号相位多样性）。

    Returns:
        dict: protocol, frame_bytes, raw_hex, apid, channel_id, params_parsed
    """
    asm: bytes = ccsds.ASM
    apid: int = ccsds.APID_ATTITUDE

    n_params: int = max(len(params), 9)
    quat_vals: list[int] = []
    gyro_vals: list[int] = []
    mode_val: int = tick % 4
    act_val: int = 0x0F

    for i in range(4):
        v: float = _sim_value(tick, i * n_params, 1.0, 0.0)
        quat_vals.append(int(max(-32768, min(32767, round(v * 32768)))))

    for i in range(3):
        v = _sim_value(tick, (4 + i) * n_params, 10.0, 0.0)
        gyro_vals.append(int(max(-32768, min(32767, round(v / 0.01)))))

    attitude_data: bytes = struct.pack(
        ">hhhhhhhBB",
        quat_vals[0], quat_vals[1], quat_vals[2], quat_vals[3],
        gyro_vals[0], gyro_vals[1], gyro_vals[2],
        mode_val, act_val,
    )

    # EPDU 主包头（6 字节）
    version: int = 0
    pkt_type: int = 0
    sec_hdr_flag: int = 0
    grouping: int = 0b01
    seq_count: int = tick & 0x3FFF

    word0: int = (version << 13) | (pkt_type << 12) | (sec_hdr_flag << 11) | apid
    word1: int = (grouping << 14) | seq_count
    data_field_len: int = len(attitude_data) + 2  # attitude + CRC
    word2: int = data_field_len - 1

    epdu_header: bytes = struct.pack(">HHH", word0, word1, word2)

    # CRC-CCITT
    crc_input: bytes = epdu_header + attitude_data
    crc_val: int = ccsds.crc_ccitt(crc_input)
    crc_bytes: bytes = struct.pack(">H", crc_val)

    epdu_packet: bytes = epdu_header + attitude_data + crc_bytes

    # CADU 帧拼接（256 字节）
    mpdu_header: bytes = bytes([0x00, 0x00, 0x0C])
    data_zone_start: int = 7
    frame: bytearray = bytearray(256)
    frame[0:4] = asm
    frame[4:7] = mpdu_header
    epdu_len: int = len(epdu_packet)
    frame[data_zone_start:data_zone_start + epdu_len] = epdu_packet
    for i in range(data_zone_start + epdu_len, 252):
        frame[i] = 0xAA
    frame[252:256] = bytes([0x00, 0x00, 0x00, 0x00])

    frame_bytes: bytes = bytes(frame)
    raw_hex: str = frame_bytes.hex().upper()

    return {
        "protocol_type": "CCSDS",
        "frame_bytes": frame_bytes,
        "raw_hex": raw_hex,
        "apid": apid,
        "channel_id": _CCSDS_CH,
        "parsed_params": [],  # 姿态参数由 manager 映射
    }


def _build_m1553b_frame(tick: int, params: list[models.TelemetryParam]) -> dict[str, Any]:
    """构建 1553B BC→RT 消息帧。

    Args:
        tick: 周期序号。
        params: 分配到此帧的参数列表。

    Returns:
        dict: 协议类型、帧字节、raw_hex、channel_id。
    """
    rt_address: int = 5
    sub_address: int = 1
    data_words: list[int] = []
    n: int = max(len(params), 4)
    for i in range(4):
        v: float = _sim_value(tick, i * n, 32767.0, 32767.0)
        data_words.append(int(v) & 0xFFFF)

    msg: dict = m1553b_mod.build_bc_rt_message(
        rt_address=rt_address,
        sub_address=sub_address,
        data_words=data_words,
        t_r=1,
    )
    frame_bytes: bytes = struct.pack(">H", msg["command_word"])
    for dw in data_words:
        frame_bytes += struct.pack(">H", dw)

    return {
        "protocol_type": "1553B",
        "frame_bytes": frame_bytes,
        "raw_hex": frame_bytes.hex().upper(),
        "apid": 0,
        "channel_id": _M1553B_CH,
        "parsed_params": [],
    }


def _build_can_frame(tick: int, params: list[models.TelemetryParam]) -> dict[str, Any]:
    """构建 CAN 标准帧。

    Args:
        tick: 周期序号。
        params: 分配到此帧的参数列表。

    Returns:
        dict: 协议类型、帧字节、raw_hex、channel_id。
    """
    can_id: int = 0x100
    dlc: int = 8
    data_bytes: bytearray = bytearray(8)
    n: int = max(len(params), 8)
    for i in range(8):
        v: float = _sim_value(tick, i * n, 127.0, 127.0)
        data_bytes[i] = int(max(0, min(255, round(v)))) & 0xFF

    frame_bytes: bytes = struct.pack(">HBB", can_id & 0x7FF, dlc, 0) + bytes(data_bytes)
    return {
        "protocol_type": "CAN",
        "frame_bytes": frame_bytes,
        "raw_hex": frame_bytes.hex().upper(),
        "apid": 0,
        "channel_id": _CAN_CH,
        "parsed_params": [],
    }


def _build_rs422_frame(tick: int, params: list[models.TelemetryParam]) -> dict[str, Any]:
    """构建 RS-422 自定义帧。

    Args:
        tick: 周期序号。
        params: 分配到此帧的参数列表。

    Returns:
        dict: 协议类型、帧字节、raw_hex、channel_id。
    """
    sat_id: int = 1
    values: list[float] = []
    n: int = max(len(params), 4)
    for i in range(min(8, max(n, 4))):
        v: float = _sim_value(tick, i * n, 50.0, 100.0)
        values.append(v)
    if not values:
        for i in range(4):
            values.append(_sim_value(tick, i * 10, 50.0, 100.0))

    frame_bytes: bytes = rs422.build_frame(satellite_id=sat_id, params=values)
    return {
        "protocol_type": "RS422",
        "frame_bytes": frame_bytes,
        "raw_hex": frame_bytes.hex().upper(),
        "apid": 0,
        "channel_id": _RS422_CH,
        "parsed_params": [],
    }


# ---------------------------------------------------------------------------
# 通道 ID 缓存（按协议类型）
# ---------------------------------------------------------------------------

_CCSDS_CH: int = 0
_M1553B_CH: int = 0
_CAN_CH: int = 0
_RS422_CH: int = 0


def _load_channel_ids(db: Session) -> None:
    """从数据库 channels 表加载各协议的 channel_id。"""
    global _CCSDS_CH, _M1553B_CH, _CAN_CH, _RS422_CH
    channels: list[models.Channel] = db.query(models.Channel).all()
    mapping: dict[str, int] = {}
    for ch in channels:
        if ch.protocol_type not in mapping:
            mapping[ch.protocol_type] = ch.id
    _CCSDS_CH = mapping.get("CCSDS", 0)
    _M1553B_CH = mapping.get("1553B", 0)
    _CAN_CH = mapping.get("CAN", 0)
    _RS422_CH = mapping.get("RS422", 0)

    # 如果某协议通道不存在则自动创建
    _ensure_channels(db)


def _ensure_channels(db: Session) -> None:
    """确保每种协议类型至少有一条 channel 记录。"""
    global _CCSDS_CH, _M1553B_CH, _CAN_CH, _RS422_CH
    needed: dict[str, tuple[str, int, str]] = {
        "CCSDS": ("CCSDS主通道", 9001, "CADU"),
        "1553B": ("1553B模拟通道", 9011, "MIL-STD-1553B"),
        "CAN": ("CAN模拟通道", 9002, "CAN 2.0B"),
        "RS422": ("RS422模拟通道", 9021, "RS-422自定义"),
    }
    satellite_id: int = 1
    # 尝试获得实际的 satellite_id
    sat: models.Satellite | None = db.query(models.Satellite).first()
    if sat is not None:
        satellite_id = sat.id

    for proto, (name, port, fmt) in needed.items():
        ch_id: int = globals()[f"_{proto}_CH".replace("1553B", "M1553B") if proto == "1553B" else f"_{proto}_CH"]
        if ch_id == 0:
            existing: models.Channel | None = db.query(models.Channel).filter(
                models.Channel.satellite_id == satellite_id,
                models.Channel.protocol_type == proto,
            ).first()
            if existing is not None:
                ch_id = existing.id
            else:
                new_ch: models.Channel = models.Channel(
                    satellite_id=satellite_id,
                    name=name,
                    protocol_type=proto,
                    ip="127.0.0.1",
                    port=port,
                    frame_format=fmt,
                    running=1,
                )
                db.add(new_ch)
                db.commit()
                db.refresh(new_ch)
                ch_id = new_ch.id
            _set_channel_global(proto, ch_id)


def _set_channel_global(proto: str, ch_id: int) -> None:
    """设置协议对应的全局 channel_id。"""
    global _CCSDS_CH, _M1553B_CH, _CAN_CH, _RS422_CH
    if proto == "CCSDS":
        _CCSDS_CH = ch_id
    elif proto == "1553B":
        _M1553B_CH = ch_id
    elif proto == "CAN":
        _CAN_CH = ch_id
    elif proto == "RS422":
        _RS422_CH = ch_id


# ---------------------------------------------------------------------------
# Simulator 主类
# ---------------------------------------------------------------------------

class FrameSimulator:
    """数据帧模拟器。

    每个周期生成全部启用参数的时间序列点，并为四类协议各构造一帧。
    """

    _FRAME_BUILDERS: dict[str, Any] = {
        "CCSDS": _build_ccsds_frame,
        "1553B": _build_m1553b_frame,
        "CAN": _build_can_frame,
        "RS422": _build_rs422_frame,
    }

    def __init__(self) -> None:
        self._params: list[models.TelemetryParam] = []
        self._param_map: dict[str, models.TelemetryParam] = {}
        self._tick: int = 0
        self._loaded: bool = False

    def load_config(self, db: Session) -> None:
        """从数据库加载已启用的遥测参数定义和通道信息。

        Args:
            db: SQLAlchemy 数据库会话。
        """
        _load_channel_ids(db)
        self._params = (
            db.query(models.TelemetryParam)
            .filter(models.TelemetryParam.enabled == 1)
            .order_by(models.TelemetryParam.id)
            .all()
        )
        self._param_map = {p.param_code: p for p in self._params}
        self._loaded = True

    @property
    def params(self) -> list[models.TelemetryParam]:
        """当前加载的启用的参数列表。"""
        return self._params

    def generate_cycle(self) -> dict[str, Any]:
        """生成一个周期的模拟数据。

        Returns:
            dict:
                {
                    "ts": datetime,
                    "tick": int,
                    "param_points": [{"satellite_id","channel_id","param_code","raw_value","value","quality"}, ...],
                    "frames": [{"protocol_type","raw_hex","apid","channel_id","frame_bytes"}, ...],
                }
        """
        tick: int = self._tick
        self._tick += 1
        ts: datetime = datetime.now()

        param_points: list[dict[str, Any]] = []
        for i, param in enumerate(self._params):
            v: float = _sim_value(tick, i, 50.0, param.offset)
            raw: int = _eng_to_raw(v, param)
            ch_id: int = _get_channel_for_param(param, i)
            param_points.append({
                "ts": ts,
                "satellite_id": param.satellite_id,
                "channel_id": ch_id,
                "param_code": param.param_code,
                "raw_value": raw,
                "value": round(v, param.precision),
                "quality": "GOOD",
            })

        # 按参数序号均分到四种协议
        n: int = len(self._params)
        q: int = max(1, n // 4) if n > 0 else 1
        groups: dict[str, list[models.TelemetryParam]] = {
            "CCSDS": self._params[0:q],
            "1553B": self._params[q:q * 2],
            "CAN": self._params[q * 2:q * 3],
            "RS422": self._params[q * 3:],
        }

        # 合并所有参数供 fallback
        all_params: list[models.TelemetryParam] = self._params

        frames: list[dict[str, Any]] = []
        for proto, builder in self._FRAME_BUILDERS.items():
            grp: list[models.TelemetryParam] = groups.get(proto, all_params)
            # 如果 DB 无参数则传入空列表，帧构建函数内部会用纯计算值生成
            if not grp:
                grp = all_params
            fr: dict[str, Any] = builder(tick, grp)
            fr["ts"] = ts
            fr["satellite_id"] = grp[0].satellite_id if grp else 1
            frames.append(fr)

        return {
            "ts": ts,
            "tick": tick,
            "param_points": param_points,
            "frames": frames,
        }


def _get_channel_for_param(param: models.TelemetryParam, idx: int) -> int:
    """按参数索引分配协议通道 ID（用于 param_point 的 channel_id）。"""
    proto_idx: int = idx % 4
    mapping: dict[int, int] = {
        0: _CCSDS_CH,
        1: _M1553B_CH,
        2: _CAN_CH,
        3: _RS422_CH,
    }
    return mapping.get(proto_idx, 0)


# 模块级单例
simulator: FrameSimulator = FrameSimulator()
