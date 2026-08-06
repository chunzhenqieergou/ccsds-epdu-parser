"""
帧解析详情模块
==============
把任意十六进制协议帧（CCSDS/1553B/CAN/RS422）解析为结构化字段列表，
供前端「整帧解析视图」与调试使用。返回统一的 fields 结构：
  [{name, value, desc}, ...] 以及 ok / message 校验状态。
"""
import struct

from ..protocols import ccsds, rs422
from ..protocols import m1553b as m1553b_mod
from ..protocols import can as can_mod


def _field(name: str, value: str, desc: str = "") -> dict:
    return {"name": name, "value": value, "desc": desc}


def parse_frame_detail(protocol_type: str, data: bytes) -> dict:
    """四协议帧 → 结构化解析结果。

    Returns:
        dict: {protocol_type, ok, message, fields: [{name, value, desc}]}
    """
    fields: list[dict] = []
    ok: bool = True
    message: str = ""

    if protocol_type == "CCSDS":
        return _parse_ccsds(data)

    if protocol_type == "1553B":
        return _parse_1553b(data)

    if protocol_type == "CAN":
        return _parse_can(data)

    if protocol_type == "RS422":
        return _parse_rs422(data)

    return {"protocol_type": protocol_type, "ok": False,
            "message": f"不支持的协议类型: {protocol_type}", "fields": []}


# ---------------------------------------------------------------------------
# CCSDS
# ---------------------------------------------------------------------------
def _parse_ccsds(data: bytes) -> dict:
    fields: list[dict] = []
    if len(data) < 11:
        return {"protocol_type": "CCSDS", "ok": False,
                "message": "CCSDS 帧长度不足", "fields": []}

    cadu = ccsds.parse_cadu_frame(data)
    asm_ok: bool = bool(cadu.get("ASM_valid"))
    fields.append(_field("帧同步 ASM", data[0:4].hex().upper(),
                         "通过" if asm_ok else "校验失败"))
    fhp: int = cadu.get("first_header_pointer", 0)
    fields.append(_field("MPDU 首包指针", str(fhp), f"数据区偏移 {7 + fhp} 字节"))

    if not asm_ok:
        return {"protocol_type": "CCSDS", "ok": False,
                "message": "ASM 帧同步标记校验失败", "fields": fields}

    zone: bytes = cadu.get("MPDU_data_zone", b"")
    if len(zone) < fhp + 6:
        return {"protocol_type": "CCSDS", "ok": True, "message": "",
                "fields": fields}
    hdr = ccsds.parse_epdu_header(zone[fhp:fhp + 6])
    fields += [
        _field("EPDU 版本号", str(hdr.get("version_number", "?"))),
        _field("EPDU 包类型", "遥测(TM)" if hdr.get("packet_type") == 0
               else "遥控(TC)", str(hdr.get("packet_type"))),
        _field("二级头标志", str(hdr.get("secondary_header_flag", "?"))),
        _field("APID", f"0x{hdr.get('APID', 0):03X}", f"十进制 {hdr.get('APID')}"),
        _field("分组标志", str(hdr.get("grouping_flags", "?"))),
        _field("包序列计数", str(hdr.get("sequence_count", "?"))),
        _field("包数据长度", str(hdr.get("packet_data_length", "?")),
               f"数据域 {hdr.get('data_field_length')} 字节"),
    ]
    dlen: int = hdr.get("data_field_length", 0)
    data_field: bytes = zone[fhp + 6:fhp + 6 + dlen]
    if len(data_field) >= 2:
        crc_recv: int = struct.unpack(">H", data_field[-2:])[0]
        crc_input: bytes = zone[fhp:fhp + 6 + dlen - 2]
        crc_calc: int = ccsds.crc_ccitt(crc_input)
        crc_ok: bool = crc_recv == crc_calc
        fields.append(_field("CRC-CCITT 校验",
                             f"收到 0x{crc_recv:04X} / 计算 0x{crc_calc:04X}",
                             "通过" if crc_ok else "失败"))
        telemetry: bytes = data_field[:-2]
        fields.append(_field("遥测数据域", telemetry.hex().upper(),
                             f"{len(telemetry)} 字节"))
        if len(telemetry) >= 16:
            for p in ccsds.parse_attitude_telemetry(telemetry[:16]):
                fields.append(_field(f"姿态·{p['name']}", p["raw_hex"],
                                     f"raw={p['raw']} → {p['eng_value']}"))
        return {"protocol_type": "CCSDS", "ok": crc_ok,
                "message": "" if crc_ok else "CRC 校验失败", "fields": fields}

    return {"protocol_type": "CCSDS", "ok": True, "message": "", "fields": fields}


# ---------------------------------------------------------------------------
# 1553B
# ---------------------------------------------------------------------------
def _parse_1553b(data: bytes) -> dict:
    fields: list[dict] = []
    if len(data) < 4:
        return {"protocol_type": "1553B", "ok": False,
                "message": "1553B 帧长度不足", "fields": []}
    cmd: int = struct.unpack(">H", data[0:2])[0]
    ci = m1553b_mod.parse_command_word(cmd)
    fields += [
        _field("命令字", f"0x{cmd:04X}", ""),
        _field("RT 地址", str(ci.get("rt_address")), "远程终端地址 5bit"),
        _field("T/R 位", "发送(BC→RT)" if ci.get("t_r") else "接收(RT→BC)"),
        _field("子地址", str(ci.get("sub_address"))),
        _field("字计数", str(ci.get("word_count")), f"数据字 {ci.get('word_count')} 个"),
    ]
    n_words: int = (len(data) - 2) // 2
    for i in range(n_words):
        w: int = struct.unpack(">H", data[2 + i * 2:4 + i * 2])[0]
        dw = m1553b_mod.parse_data_word(w)
        fields.append(_field(f"数据字 {i + 1}", f"0x{w:04X}",
                             f"data={dw.get('data')} 奇偶位={dw.get('parity')}"))
    return {"protocol_type": "1553B", "ok": True, "message": "", "fields": fields}


# ---------------------------------------------------------------------------
# CAN
# ---------------------------------------------------------------------------
def _parse_can(data: bytes) -> dict:
    fields: list[dict] = []
    if len(data) < 4:
        return {"protocol_type": "CAN", "ok": False,
                "message": "CAN 帧长度不足", "fields": []}
    arb: int = struct.unpack(">H", data[0:2])[0]
    dlc: int = data[2]
    payload: bytes = data[4:4 + dlc]
    parsed = can_mod.parse_can_std_frame(arb, dlc, payload)
    fields += [
        _field("帧类型", "标准帧 (11位ID)", parsed.get("id_type")),
        _field("仲裁 ID", f"0x{parsed.get('id', 0):03X}", f"十进制 {parsed.get('id')}"),
        _field("RTR", str(parsed.get("rtr", 0)), "0=数据帧 1=远程帧"),
        _field("DLC", str(dlc), f"数据长度 {dlc} 字节"),
        _field("数据域", payload.hex().upper(),
               " ".join(str(b) for b in payload)),
    ]
    return {"protocol_type": "CAN", "ok": True, "message": "", "fields": fields}


# ---------------------------------------------------------------------------
# RS422
# ---------------------------------------------------------------------------
def _parse_rs422(data: bytes) -> dict:
    fields: list[dict] = []
    parsed = rs422.parse_frame(data)
    if parsed is None:
        return {"protocol_type": "RS422", "ok": False,
                "message": "帧头不匹配或 CRC 校验失败", "fields": []}
    crc_ok: bool = bool(parsed.get("crc_ok", False))
    length: int = parsed.get("length", 0)
    # 与 protocols/rs422.parse_frame 保持一致：CRC 计算不含帧头，含长度字段与参数数据
    crc_input: bytes = data[2:2 + length]
    fields += [
        _field("帧头", data[0:2].hex().upper(), "0xAA 0x55"),
        _field("帧长度", str(length), ""),
        _field("卫星 ID", str(parsed.get("satellite_id")), ""),
        _field("CRC-16 校验",
               f"收到 0x{parsed.get('crc'):04X} / 计算 0x{rs422.crc16_modbus(crc_input):04X}",
               "通过" if crc_ok else "失败"),
    ]
    for i, v in enumerate(parsed.get("params", [])):
        fields.append(_field(f"参数 {i + 1}", f"{v:.6f}", "float32 大端"))
    return {"protocol_type": "RS422", "ok": crc_ok,
            "message": "" if crc_ok else "CRC 校验失败", "fields": fields}
