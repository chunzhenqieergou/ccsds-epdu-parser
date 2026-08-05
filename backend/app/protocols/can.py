"""
CAN 总线协议解析模块

支持标准帧(11-bit ID)和扩展帧(29-bit ID)解析，以及小位段信号提取。
"""

import struct

STD_ID_MASK: int = 0x7FF
"""标准帧 11 位 ID 掩码"""

EXT_ID_MASK: int = 0x1FFFFFFF
"""扩展帧 29 位 ID 掩码"""


def parse_can_std_frame(arb_id: int, dlc: int, data_bytes: bytes) -> dict:
    """
    解析 CAN 标准帧（11 位标识符）。

    Args:
        arb_id: 仲裁域 ID (11 位有效)。
        dlc: 数据长度码 (0-8)。
        data_bytes: 数据字节。

    Returns:
        dict: id, id_type('STD'), rtr, dlc, data, comment。
    """
    rtr = (arb_id >> 12) & 0x01 if arb_id > 0x7FF else 0
    can_id = arb_id & STD_ID_MASK
    data = data_bytes[:min(dlc, 8)]
    return {
        "id": can_id,
        "id_type": "STD",
        "rtr": rtr,
        "dlc": dlc,
        "data": data,
        "comment": f"标准帧 ID=0x{can_id:03X} DLC={dlc}",
    }


def parse_can_ext_frame(arb_id: int, dlc: int, data_bytes: bytes) -> dict:
    """
    解析 CAN 扩展帧（29 位标识符）。

    Args:
        arb_id: 仲裁域 ID (29 位有效)。
        dlc: 数据长度码 (0-8)。
        data_bytes: 数据字节。

    Returns:
        dict: id, id_type('EXT'), base_id(11b), srr, ide, ext_id(18b), rtr, dlc, data, comment。
    """
    can_id = arb_id & EXT_ID_MASK
    base_id = (can_id >> 18) & 0x7FF
    ext_id = can_id & 0x3FFFF
    srr = (can_id >> 17) & 0x01
    ide = 1
    rtr = 0
    data = data_bytes[:min(dlc, 8)]
    return {
        "id": can_id,
        "id_type": "EXT",
        "base_id": base_id,
        "srr": srr,
        "ide": ide,
        "ext_id": ext_id,
        "rtr": rtr,
        "dlc": dlc,
        "data": data,
        "comment": f"扩展帧 ID=0x{can_id:08X} DLC={dlc} base=0x{base_id:03X} ext=0x{ext_id:05X}",
    }


def decode_can_signal(
    byte_offset: int,
    start_bit: int,
    length: int,
    data_bytes: bytes,
    signed: bool = False,
    scale: float = 1.0,
    offset: float = 0.0,
) -> float:
    """
    从 CAN 报文数据域中提取信号值（小端位序 Intel/Little-Endian）。

    位索引按 CAN DBC 约定: byte_offset 为起始字节，start_bit 为该字节内起始位(0-7)，
    位跨字节时向高位字节延伸。

    Args:
        byte_offset: 起始字节在 data_bytes 中的偏移 (0-based)。
        start_bit: 起始位在起始字节中的位置 (0-7, LSB=0)。
        length: 信号位宽 (1-64)。
        data_bytes: 报文数据字节。
        signed: 是否带符号解释。
        scale: 缩放因子。
        offset: 偏移量。

    Returns:
        float: 信号工程值 = (raw * scale) + offset。
    """
    if not data_bytes:
        return 0.0

    raw = 0
    bit_pos = 0
    total_bits = byte_offset * 8 + start_bit

    for _ in range(length):
        byte_idx = total_bits // 8
        bit_idx = total_bits % 8
        if byte_idx < len(data_bytes):
            if data_bytes[byte_idx] & (1 << bit_idx):
                raw |= 1 << bit_pos
        total_bits += 1
        bit_pos += 1

    if signed and (raw & (1 << (length - 1))):
        raw -= 1 << length

    return raw * scale + offset


if __name__ == "__main__":
    print("=== CAN 协议模块示例 ===")

    std = parse_can_std_frame(arb_id=0x123, dlc=8, data_bytes=bytes([0x01, 0x02, 0x03, 0x04, 0x00, 0x00, 0x00, 0x00]))
    print(f"标准帧: {std['comment']}, data={std['data'].hex(' ').upper()}")

    ext = parse_can_ext_frame(arb_id=0x18DAF110, dlc=8, data_bytes=bytes([0x11, 0x22, 0x33, 0x44, 0x00, 0x00, 0x00, 0x00]))
    print(f"扩展帧: {ext['comment']}")

    test_data = bytes([0x12, 0x34, 0x56, 0x78, 0x00, 0x00, 0x00, 0x00])
    val = decode_can_signal(byte_offset=0, start_bit=0, length=8, data_bytes=test_data)
    print(f"信号提取: byte_offset=0, start_bit=0, length=8, data=0x12 → value={val}")

    val2 = decode_can_signal(byte_offset=1, start_bit=0, length=4, data_bytes=test_data)
    print(f"信号提取: byte_offset=1, start_bit=0, length=4, data=0x34 → value={val2} (0x34的低4位=4)")

    val3 = decode_can_signal(byte_offset=0, start_bit=8, length=16, data_bytes=test_data, scale=0.1)
    print(f"信号提取: byte_offset=0, start_bit=8, length=16 → raw=0x3412={0x3412}, scaled={val3}")
