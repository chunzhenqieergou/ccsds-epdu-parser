"""
CCSDS Space Packet 协议解析模块 (CCSDS 133.0-B-1 简化) + CADU 帧

参考实现: parse_epdu3.py（姿态控制遥测解析器），本模块将其核心逻辑重构为可复用函数。
"""

import struct

ASM: bytes = b"\x1A\xCF\xFC\x1D"
"""CADU 帧同步标记 (Attached Sync Marker)"""

APID_ATTITUDE: int = 0x003
"""姿态控制分系统 APID"""

ATTITUDE_MODE: dict[int, str] = {0: "待机", 1: "三轴稳态", 2: "自旋", 3: "机动"}
"""姿态模式枚举"""

ACTUATOR_BITS: dict[int, str] = {
    0: "动量轮A使能",
    1: "动量轮B使能",
    2: "动量轮C使能",
    3: "推力器组1使能",
    4: "推力器组2使能",
    5: "磁力矩器使能",
    6: "太阳帆板驱动",
    7: "预留",
}
"""执行机构状态位定义"""


def hex_to_bytes(hex_str: str) -> bytes:
    """将十六进制字符串（可含换行/空格）转换为字节数据。"""
    return bytes.fromhex(hex_str.replace("\n", " ").replace("  ", " ").strip())


def crc_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """
    计算 CRC-CCITT 校验值。

    多项式 0x1021，初始值 0xFFFF，不反射。
    CCSDS 标准 Packet Error Control 算法。
    """
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc


def parse_cadu_frame(frame: bytes) -> dict:
    """
    解析 CADU 帧。

    Args:
        frame: 原始 CADU 帧字节（256 字节）。

    Returns:
        dict: ASM, ASM_valid, first_header_pointer, frame_length 等字段。
    """
    result: dict = {}

    asm = frame[0:4]
    result["ASM"] = asm
    result["ASM_valid"] = asm == ASM
    result["frame_length"] = len(frame)

    mpdu_header = frame[4:7]
    result["MPDU_header"] = mpdu_header
    first_header_ptr = struct.unpack(">H", mpdu_header[1:3])[0] & 0x07FF if len(mpdu_header) >= 3 else 0
    result["first_header_pointer"] = first_header_ptr

    if len(frame) >= 7 + 245:
        result["MPDU_data_zone"] = frame[7:7 + 245]
    else:
        result["MPDU_data_zone"] = b""

    if len(frame) >= 4:
        result["RS_checksum"] = frame[-4:]
    else:
        result["RS_checksum"] = b""

    return result


def parse_epdu_header(header: bytes) -> dict:
    """
    解析 EPDU 主包头（6 字节）。

    结构: 版本号(3b) | 类型(1b) | 二级头标志(1b) | APID(11b) ||
           分组标志(2b) | 序列计数(14b) || 包长(16b)

    Args:
        header: 6 字节 EPDU 主包头。

    Returns:
        dict: version_number, packet_type, secondary_header_flag, APID,
              grouping_flags, sequence_count, packet_data_length, data_field_length。
    """
    result: dict = {}
    if len(header) < 6:
        return result

    word0 = struct.unpack(">H", header[0:2])[0]
    word1 = struct.unpack(">H", header[2:4])[0]
    word2 = struct.unpack(">H", header[4:6])[0]

    result["version_number"] = (word0 >> 13) & 0x07
    result["packet_type"] = (word0 >> 12) & 0x01
    result["secondary_header_flag"] = (word0 >> 11) & 0x01
    result["APID"] = word0 & 0x07FF

    result["grouping_flags"] = (word1 >> 14) & 0x03
    result["sequence_count"] = word1 & 0x3FFF

    result["packet_data_length"] = word2
    result["data_field_length"] = word2 + 1

    return result


def parse_attitude_telemetry(data: bytes) -> list[dict]:
    """
    解析姿态控制系统遥测参数（EPDU 包3 专用参数表）。

    数据域布局（16 字节）:
        字节 0-1:  四元数Q0 (int16 BE) → eng = raw / 32768
        字节 2-3:  四元数Q1 (int16 BE) → eng = raw / 32768
        字节 4-5:  四元数Q2 (int16 BE) → eng = raw / 32768
        字节 6-7:  四元数Q3 (int16 BE) → eng = raw / 32768
        字节 8-9:  角速度X  (int16 BE) → eng = raw * 0.01
        字节 10-11:角速度Y  (int16 BE) → eng = raw * 0.01
        字节 12-13:角速度Z  (int16 BE) → eng = raw * 0.01
        字节 14:   姿态模式  (uint8)  → 枚举
        字节 15:   执行机构状态(uint8) → 按位解析

    Args:
        data: 遥测数据字节（至少 16 字节）。

    Returns:
        list[dict]: 每个参数包含 name, offset, raw, raw_hex, eng_value, formula。
    """
    params: list[dict] = []

    quaternion_labels = ["Q0 (W)", "Q1 (X)", "Q2 (Y)", "Q3 (Z)"]
    for i in range(4):
        offset = i * 2
        raw = struct.unpack(">h", data[offset:offset + 2])[0]
        eng_value = raw / 32768.0
        params.append({
            "name": f"四元数{quaternion_labels[i]}",
            "offset": f"字节{offset}-{offset + 1}",
            "raw": raw,
            "raw_hex": data[offset:offset + 2].hex().upper(),
            "eng_value": f"{eng_value:.6f}",
            "formula": "raw / 32768",
        })

    gyro_labels = ["X", "Y", "Z"]
    for i in range(3):
        offset = 8 + i * 2
        raw = struct.unpack(">h", data[offset:offset + 2])[0]
        eng_value = raw * 0.01
        params.append({
            "name": f"角速度{gyro_labels[i]}",
            "offset": f"字节{offset}-{offset + 1}",
            "raw": raw,
            "raw_hex": data[offset:offset + 2].hex().upper(),
            "eng_value": f"{eng_value:.2f} °/s",
            "formula": "raw × 0.01",
        })

    offset = 14
    raw = data[offset]
    mode_str = ATTITUDE_MODE.get(raw, f"未知({raw})")
    params.append({
        "name": "姿态模式",
        "offset": f"字节{offset}",
        "raw": raw,
        "raw_hex": f"{data[offset]:02X}",
        "eng_value": mode_str,
        "formula": "枚举: 0=待机,1=三轴稳态,2=自旋,3=机动",
    })

    offset = 15
    raw = data[offset]
    active_bits = [ACTUATOR_BITS.get(bit, f"位{bit}") for bit in range(8) if raw & (1 << bit)]
    params.append({
        "name": "执行机构状态",
        "offset": f"字节{offset}",
        "raw": raw,
        "raw_hex": f"{data[offset]:02X}",
        "eng_value": f"0b{raw:08b} → {'; '.join(active_bits) if active_bits else '无使能'}",
        "formula": "按位解析(8位标志)",
    })

    return params


if __name__ == "__main__":
    CADU_FRAME3_HEX = """
    1A CF FC 1D 00 00 0C AA AA AA AA AA AA AA AA AA AA AA AA 00 03 C0 03 00 11
    1A 1B 1C 1D 1E 1F 20 21 22 23 24 25 26 27 28 29 D0 80 AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
    00 00 00 00
    """

    print("=== CCSDS 协议模块示例 ===")
    frame = hex_to_bytes(CADU_FRAME3_HEX)[:256]

    cadu = parse_cadu_frame(frame)
    print(f"CADU: ASM_valid={cadu['ASM_valid']}, first_header_pointer={cadu['first_header_pointer']}")

    mpdu_zone_start = 7
    epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
    epdu_header_bytes = frame[epdu_offset:epdu_offset + 6]
    hdr = parse_epdu_header(epdu_header_bytes)
    print(f"EPDU: APID=0x{hdr['APID']:03X}, sequence_count={hdr['sequence_count']}")

    data_field_start = epdu_offset + 6
    data_field = frame[data_field_start:data_field_start + hdr["data_field_length"]]
    crc_received = struct.unpack(">H", data_field[-2:])[0]
    crc_input = frame[epdu_offset:data_field_start + hdr["data_field_length"] - 2]
    crc_calc = crc_ccitt(crc_input)
    print(f"CRC: received=0x{crc_received:04X}, calculated=0x{crc_calc:04X}, ok={crc_received == crc_calc}")

    telemetry_data = data_field[:-2]
    params = parse_attitude_telemetry(telemetry_data)
    for p in params:
        print(f"  {p['name']:<16} raw={p['raw']:>8} eng={p['eng_value']}")
