"""
MIL-STD-1553B 数据总线协议解析模块

1553B 字格式:
  命令字:  RT地址(5b) | T/R(1b) | 子地址/方式码(5b) | 字计数/方式码(5b)
  数据字:  数据(16b)
  状态字:  RT地址(5b) | 消息错误(1b) | 仪表(1b) | 服务请求(1b) | 保留(3b) | 广播(1b) | 忙(1b) | 子系统标志(1b) | 终端标志(1b) | 奇偶(1b)
"""

import struct

COMMAND_SYNC_HEADER: int = 0x03
"""命令字同步头 (bit[15:14] = 11 表示命令/状态)"""

STATUS_SYNC_HEADER: int = 0x03
"""状态字同步头 (bit[15:14] = 11 表示命令/状态)"""


def parse_command_word(w: int) -> dict:
    """
    解析 1553B 命令字（16 位无符号整数）。

    Args:
        w: 16 位命令字。

    Returns:
        dict: rt_address(5b), t_r(1b, 0=接收/1=发送),
              sub_address(5b), word_count(5b), sync_header(2b)。
    """
    if not (0 <= w <= 0xFFFF):
        return {}
    return {
        "sync_header": (w >> 14) & 0x03,
        "rt_address": (w >> 9) & 0x1F,
        "t_r": (w >> 8) & 0x01,
        "sub_address": (w >> 3) & 0x1F,
        "word_count": w & 0x1F,
    }


def parse_data_word(w: int) -> dict:
    """
    解析 1553B 数据字（16 位无符号整数）。

    Args:
        w: 16 位数据字。

    Returns:
        dict: data(16b), parity(1b)。
    """
    if not (0 <= w <= 0xFFFF):
        return {}
    parity = bin(w).count("1") % 2
    return {
        "data": w,
        "parity": parity,
        "sync_header": (w >> 14) & 0x03,
    }


def parse_status_word(w: int) -> dict:
    """
    解析 1553B 状态字（16 位无符号整数）。

    Args:
        w: 16 位状态字。

    Returns:
        dict: rt_address, message_error, instrument, service, busy,
              broadcast, terminal_flag, parity 等字段。
    """
    if not (0 <= w <= 0xFFFF):
        return {}
    return {
        "sync_header": (w >> 14) & 0x03,
        "rt_address": (w >> 10) & 0x0F,
        "message_error": (w >> 9) & 0x01,
        "instrument": (w >> 8) & 0x01,
        "service": (w >> 7) & 0x01,
        "reserved": (w >> 4) & 0x07,
        "broadcast": (w >> 3) & 0x01,
        "busy": (w >> 2) & 0x01,
        "subsystem_flag": (w >> 1) & 0x01,
        "terminal_flag": w & 0x01,
        "parity": bin(w).count("1") % 2,
    }


def build_bc_rt_message(
    rt_address: int,
    sub_address: int,
    data_words: list[int],
    t_r: int = 1,
) -> dict:
    """
    组装 BC→RT 消息。

    Args:
        rt_address: 远程终端地址 (0-31)。
        sub_address: 子地址 (0-31)。
        data_words: 数据字列表（每个 16 位无符号）。
        t_r: T/R 位，0=接收，1=发送（默认 1 表示 BC→RT 发送）。

    Returns:
        dict: command_word, command_parsed, data_words, data_words_parsed,
              word_count, 结构完整的消息描述。
    """
    word_count = len(data_words) & 0x1F
    cmd_raw = (COMMAND_SYNC_HEADER << 14) | ((rt_address & 0x1F) << 9) | ((t_r & 0x01) << 8) | ((sub_address & 0x1F) << 3) | (word_count & 0x1F)

    return {
        "command_word": cmd_raw,
        "command_parsed": parse_command_word(cmd_raw),
        "data_words": data_words,
        "data_words_parsed": [parse_data_word(dw) for dw in data_words],
        "word_count": word_count,
        "description": f"BC→RT{rt_address}, 子地址{sub_address}, T/R={t_r}(发送), 数据字数={word_count}",
    }


if __name__ == "__main__":
    print("=== MIL-STD-1553B 协议模块示例 ===")

    cmd = parse_command_word(0x8823)
    print(f"命令字解析: rt_address={cmd['rt_address']}, t_r={cmd['t_r']}, sub_address={cmd['sub_address']}, word_count={cmd['word_count']}")

    data = parse_data_word(0xA5F0)
    print(f"数据字解析: data=0x{data['data']:04X}, parity={data['parity']}")

    status = parse_status_word(0x4800)
    print(f"状态字解析: rt_address={status['rt_address']}, message_error={status['message_error']}, busy={status['busy']}")

    msg = build_bc_rt_message(rt_address=5, sub_address=1, data_words=[0x1234, 0x5678])
    print(f"BC→RT消息: {msg['description']}")
    print(f"  命令字=0x{msg['command_word']:04X}")
    print(f"  数据字={[f'0x{dw:04X}' for dw in msg['data_words']]}")
