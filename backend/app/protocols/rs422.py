"""
RS-422 自定义串口协议解析模块

帧格式: 帧头(2B: 0xAA 0x55) + 帧长(2B, 大端, 不含帧头) + 卫星ID(1B) +
        参数数据(N × 4B float 大端) + CRC-16/MODBUS(2B)

帧长字段 = 卫星ID(1) + N×4 + CRC(2) 的总字节数。
"""

import struct

FRAME_HEADER: bytes = b"\xAA\x55"
"""帧同步头"""

FRAME_HEADER_LEN: int = 2
"""帧头长度"""

LENGTH_FIELD_LEN: int = 2
"""帧长字段长度（大端无符号短整型）"""

SAT_ID_LEN: int = 1
"""卫星 ID 长度"""

CRC_LEN: int = 2
"""CRC-16/MODBUS 长度"""

MIN_FRAME_LEN: int = FRAME_HEADER_LEN + LENGTH_FIELD_LEN + SAT_ID_LEN + CRC_LEN
"""最小帧长度: 帧头(2) + 帧长(2) + 卫星ID(1) + CRC(2) = 7"""


def crc16_modbus(data: bytes) -> int:
    """
    计算 CRC-16/MODBUS 校验值。

    多项式 0x8005，初始值 0xFFFF，输入/输出不反射。

    Args:
        data: 待计算的数据字节。

    Returns:
        int: 16 位无符号 CRC 值。
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc = crc >> 1
    return crc & 0xFFFF


def parse_frame(frame: bytes) -> dict | None:
    """
    解析完整 RS-422 帧。

    Args:
        frame: 完整帧字节（不含帧头外的多余字节）。

    Returns:
        dict | None: 解析结果 {header, length, satellite_id, params, crc, crc_ok}，
                     帧头不匹配或 CRC 错误返回 None。
    """
    if len(frame) < MIN_FRAME_LEN:
        return None

    header = frame[0:FRAME_HEADER_LEN]
    if header != FRAME_HEADER:
        return None

    payload_length = struct.unpack(">H", frame[FRAME_HEADER_LEN:FRAME_HEADER_LEN + LENGTH_FIELD_LEN])[0]
    expected_total = FRAME_HEADER_LEN + LENGTH_FIELD_LEN + payload_length
    if len(frame) < expected_total:
        return None

    satellite_id = frame[4]
    params_data_len = payload_length - SAT_ID_LEN - CRC_LEN
    if params_data_len < 0:
        return None

    params_data = frame[5:5 + params_data_len]
    crc_received = struct.unpack(">H", frame[5 + params_data_len:5 + params_data_len + CRC_LEN])[0]

    crc_input = frame[FRAME_HEADER_LEN:FRAME_HEADER_LEN + LENGTH_FIELD_LEN + payload_length - CRC_LEN]
    crc_calc = crc16_modbus(crc_input)

    params: list[float] = []
    for i in range(0, len(params_data), 4):
        if i + 4 <= len(params_data):
            params.append(struct.unpack(">f", params_data[i:i + 4])[0])

    return {
        "header": header,
        "length": payload_length,
        "satellite_id": satellite_id,
        "params": params,
        "crc": crc_received,
        "crc_ok": crc_received == crc_calc,
    }


class Rs422Parser:
    """
    RS-422 逐字节状态机组帧器。

    用法:
        parser = Rs422Parser()
        for byte in stream:
            result = parser.feed(byte)
            if result:
                process(result)
    """

    _STATE_IDLE: int = 0
    _STATE_HEADER1: int = 1
    _STATE_HEADER2: int = 2
    _STATE_LENGTH: int = 3
    _STATE_PAYLOAD: int = 4

    def __init__(self) -> None:
        self._state: int = self._STATE_IDLE
        self._buffer: bytearray = bytearray()

    def feed(self, byte: int) -> dict | None:
        """
        喂入一个字节，若完成一帧则返回解析结果，否则返回 None。

        Args:
            byte: 单字节 (0-255)。

        Returns:
            dict | None: 完整帧解析结果，或 None。
        """
        b = byte & 0xFF
        self._buffer.append(b)

        if self._state == self._STATE_IDLE:
            if b == 0xAA:
                self._state = self._STATE_HEADER1
            else:
                self._buffer.clear()

        elif self._state == self._STATE_HEADER1:
            if b == 0x55:
                self._state = self._STATE_HEADER2
            elif b == 0xAA:
                self._buffer = bytearray([0xAA])
                self._state = self._STATE_HEADER1
            else:
                self._buffer.clear()
                self._state = self._STATE_IDLE

        elif self._state == self._STATE_HEADER2:
            if len(self._buffer) >= FRAME_HEADER_LEN + LENGTH_FIELD_LEN:
                payload_length = struct.unpack(">H", self._buffer[FRAME_HEADER_LEN:FRAME_HEADER_LEN + LENGTH_FIELD_LEN])[0]
                self._state = self._STATE_LENGTH
                return self._try_complete(payload_length)
            return None

        elif self._state == self._STATE_LENGTH:
            return self._try_complete_from_buffer()

        return None

    def _try_complete(self, payload_length: int) -> dict | None:
        expected = FRAME_HEADER_LEN + LENGTH_FIELD_LEN + payload_length
        return self._check_complete(expected)

    def _try_complete_from_buffer(self) -> dict | None:
        if len(self._buffer) < FRAME_HEADER_LEN + LENGTH_FIELD_LEN:
            return None
        payload_length = struct.unpack(">H", self._buffer[FRAME_HEADER_LEN:FRAME_HEADER_LEN + LENGTH_FIELD_LEN])[0]
        expected = FRAME_HEADER_LEN + LENGTH_FIELD_LEN + payload_length
        return self._check_complete(expected)

    def _check_complete(self, expected: int) -> dict | None:
        if len(self._buffer) >= expected:
            frame_bytes = bytes(self._buffer[:expected])
            result = parse_frame(frame_bytes)
            self._buffer = self._buffer[expected:]
            self._state = self._STATE_IDLE
            if result is not None and result["crc_ok"]:
                return result
        return None

    def reset(self) -> None:
        """重置解析器状态。"""
        self._state = self._STATE_IDLE
        self._buffer.clear()


def build_frame(satellite_id: int, params: list[float]) -> bytes:
    """
    构建 RS-422 帧。

    Args:
        satellite_id: 卫星 ID (0-255)。
        params: 参数列表（float）。

    Returns:
        bytes: 完整帧字节。
    """
    params_data = b"".join(struct.pack(">f", p) for p in params)
    payload_length = SAT_ID_LEN + len(params_data) + CRC_LEN
    header = FRAME_HEADER
    length_bytes = struct.pack(">H", payload_length)
    sat_byte = struct.pack("B", satellite_id)

    crc_input = length_bytes + sat_byte + params_data
    crc = struct.pack(">H", crc16_modbus(crc_input))

    return header + length_bytes + sat_byte + params_data + crc


if __name__ == "__main__":
    print("=== RS-422 协议模块示例 ===")

    frame = build_frame(satellite_id=1, params=[1.0, 2.5, 3.14])
    print(f"构建帧: {frame.hex(' ').upper()}")

    result = parse_frame(frame)
    if result:
        print(f"解析结果: header_valid={result['header'] == FRAME_HEADER}, "
              f"satellite_id={result['satellite_id']}, "
              f"params={result['params']}, "
              f"crc_ok={result['crc_ok']}")

    print("\n逐字节日志:")
    parser = Rs422Parser()
    for i, b in enumerate(frame):
        res = parser.feed(b)
        if res:
            print(f"  字节{i}: 完成帧 satellite_id={res['satellite_id']}, crc_ok={res['crc_ok']}")

    corrupted = bytearray(frame)
    corrupted[-3] ^= 0xFF
    bad_result = parse_frame(bytes(corrupted))
    print(f"\n坏CRC帧: crc_ok={bad_result['crc_ok']} (应为False)")
