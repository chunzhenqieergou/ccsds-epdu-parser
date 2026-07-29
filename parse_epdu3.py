#!/usr/bin/env python3
"""
CCSDS EPDU 包3 解析器 — 姿态控制系统遥测
==========================================
根据 CCSDS 协议文档，从 CADU 帧中提取并解析 EPDU 包3（APID=0x003）。
解析流程：CADU帧同步 → MPDU头 → EPDU包头 → CRC校验 → 遥测参数工程值转换
"""

import struct

# ============================================================
# 1. 原始数据：CADU 帧3（姿态控制系统遥测，256 字节）
# ============================================================
# 来源：CCSDS协议文档「CADU帧3 — 姿态控制系统遥测EPDU包」
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
00 00 00 00
"""

# ASM 同步标记
ASM = bytes([0x1A, 0xCF, 0xFC, 0x1D])

# 姿态模式枚举
ATTITUDE_MODE = {0: "待机", 1: "三轴稳态", 2: "自旋", 3: "机动"}

# 执行机构状态位定义
ACTUATOR_BITS = {
    0: "动量轮A使能",
    1: "动量轮B使能",
    2: "动量轮C使能",
    3: "推力器组1使能",
    4: "推力器组2使能",
    5: "磁力矩器使能",
    6: "太阳帆板驱动",
    7: "预留",
}


def hex_to_bytes(hex_str: str) -> bytes:
    """将十六进制字符串转换为字节数据"""
    return bytes.fromhex(hex_str.replace("\n", " ").replace("  ", " ").strip())


def crc_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """
    计算 CRC-CCITT 校验值（多项式 0x1021，初始值 0xFFFF，不反射）
    CCSDS 标准使用的 Packet Error Control 算法
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
    解析 CADU 帧
    返回: ASM, MPDU头, 首包头指针, MPDU数据区, RS校验
    """
    result = {}

    # 步骤1: ASM 同步头检测（4字节）
    asm = frame[0:4]
    result["ASM"] = asm
    result["ASM_valid"] = (asm == ASM)

    # 步骤2: 帧长度验证
    result["frame_length"] = len(frame)

    # 步骤3: 读取 MPDU 头（3字节）
    mpdu_header = frame[4:7]
    result["MPDU_header"] = mpdu_header
    # MPDU Header: 1字节版本/保留 + 2字节首包头指针
    # 文档定义: MPDU Header[23:16] 为版本/保留, MPDU Header[15:0] 为首包头指针
    first_header_ptr = struct.unpack(">H", mpdu_header[1:3])[0]
    result["first_header_pointer"] = first_header_ptr

    # MPDU 数据区（245字节）
    mpdu_data_zone = frame[7:7 + 245]
    result["MPDU_data_zone"] = mpdu_data_zone

    # RS校验（末尾4字节，可选）
    result["RS_checksum"] = frame[-4:]

    return result


def parse_epdu_header(header: bytes) -> dict:
    """
    解析 EPDU 主包头（6字节）
    结构: 版本号(3b) | 类型(1b) | 二级头标志(1b) | APID(11b) || 分组标志(2b) | 序列计数(14b) || 包长(16b)
    """
    result = {}

    word0 = struct.unpack(">H", header[0:2])[0]
    word1 = struct.unpack(">H", header[2:4])[0]
    word2 = struct.unpack(">H", header[4:6])[0]

    # 第一个16位字
    result["version_number"] = (word0 >> 13) & 0x07       # 3 bits
    result["packet_type"] = (word0 >> 12) & 0x01           # 1 bit: 0=遥测, 1=遥控
    result["secondary_header_flag"] = (word0 >> 11) & 0x01 # 1 bit
    result["APID"] = word0 & 0x07FF                        # 11 bits

    # 第二个16位字
    result["grouping_flags"] = (word1 >> 14) & 0x03        # 2 bits: 11=独立包
    result["sequence_count"] = word1 & 0x3FFF              # 14 bits

    # 第三个16位字
    result["packet_data_length"] = word2                    # 16 bits: 数据域长度 - 1

    # 计算实际数据域长度
    result["data_field_length"] = word2 + 1

    return result


def parse_attitude_telemetry(data: bytes) -> list:
    """
    解析姿态控制系统遥测参数（EPDU包3专用参数表）
    数据域布局:
      字节0-1:  四元数Q0 (int16 BE)  → Q = raw / 32768
      字节2-3:  四元数Q1 (int16 BE)  → Q = raw / 32768
      字节4-5:  四元数Q2 (int16 BE)  → Q = raw / 32768
      字节6-7:  四元数Q3 (int16 BE)  → Q = raw / 32768
      字节8-9:  角速度X  (int16 BE)  → °/s = raw × 0.01
      字节10-11:角速度Y  (int16 BE)  → °/s = raw × 0.01
      字节12-13:角速度Z  (int16 BE)  → °/s = raw × 0.01
      字节14:   姿态模式  (uint8枚举) → 0=待机,1=三轴稳态,2=自旋,3=机动
      字节15:   执行机构状态(uint8)   → 按位解析
    """
    params = []

    # 四元数 Q0~Q3
    quaternion_labels = ["Q0 (W)", "Q1 (X)", "Q2 (Y)", "Q3 (Z)"]
    for i in range(4):
        offset = i * 2
        raw = struct.unpack(">h", data[offset:offset + 2])[0]  # int16 BE (有符号)
        eng_value = raw / 32768.0
        params.append({
            "name": f"四元数{quaternion_labels[i]}",
            "offset": f"字节{offset}-{offset+1}",
            "raw": raw,
            "raw_hex": data[offset:offset + 2].hex().upper(),
            "eng_value": f"{eng_value:.6f}",
            "formula": "raw / 32768",
        })

    # 角速度 X/Y/Z
    gyro_labels = ["X", "Y", "Z"]
    for i in range(3):
        offset = 8 + i * 2
        raw = struct.unpack(">h", data[offset:offset + 2])[0]  # int16 BE (有符号)
        eng_value = raw * 0.01
        params.append({
            "name": f"角速度{gyro_labels[i]}",
            "offset": f"字节{offset}-{offset+1}",
            "raw": raw,
            "raw_hex": data[offset:offset + 2].hex().upper(),
            "eng_value": f"{eng_value:.2f} °/s",
            "formula": "raw × 0.01",
        })

    # 姿态模式
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

    # 执行机构状态（按位解析）
    offset = 15
    raw = data[offset]
    active_bits = []
    for bit in range(8):
        if raw & (1 << bit):
            active_bits.append(ACTUATOR_BITS.get(bit, f"位{bit}"))
    params.append({
        "name": "执行机构状态",
        "offset": f"字节{offset}",
        "raw": raw,
        "raw_hex": f"{data[offset]:02X}",
        "eng_value": f"0b{raw:08b} → {'; '.join(active_bits) if active_bits else '无使能'}",
        "formula": "按位解析(8位标志)",
    })

    return params


def print_separator(title: str, char="=", width=72):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def main():
    # ============================================================
    # 步骤 0: 加载原始 CADU 帧
    # ============================================================
    frame = hex_to_bytes(CADU_FRAME3_HEX)
    # 截取前256字节（文档中AA填充为示意，标准CADU帧固定256字节）
    frame = frame[:256]
    print_separator("CCSDS EPDU 包3 解析 — 姿态控制系统遥测")
    print(f"原始帧长度: {len(frame)} 字节")
    print(f"原始帧前32字节: {frame[:32].hex(' ').upper()}")

    # ============================================================
    # 步骤 1: CADU 帧解析
    # ============================================================
    print_separator("步骤 1-2: ASM 同步头检测 & 帧长度验证")
    cadu = parse_cadu_frame(frame)

    print(f"  ASM 同步头:      {cadu['ASM'].hex(' ').upper()}")
    print(f"  ASM 验证:        {'✓ 匹配 0x1ACFFC1D' if cadu['ASM_valid'] else '✗ 不匹配!'}")
    print(f"  帧长度:          {cadu['frame_length']} 字节 {'✓' if cadu['frame_length'] == 256 else '✗ (应为256)'}")

    # ============================================================
    # 步骤 3: MPDU 头解析
    # ============================================================
    print_separator("步骤 3: MPDU 头解析（3字节）")
    mpdu = cadu["MPDU_header"]
    print(f"  MPDU Header:     {mpdu.hex(' ').upper()}")
    print(f"  版本/保留字节:   0x{mpdu[0]:02X}")
    print(f"  首包头指针:      0x{cadu['first_header_pointer']:04X} = {cadu['first_header_pointer']}")
    print(f"  → 第一个 EPDU 包在 MPDU 数据区内偏移 {cadu['first_header_pointer']} 字节处")

    # ============================================================
    # 步骤 4: 定位 EPDU 包
    # ============================================================
    print_separator("步骤 4: 定位 EPDU 包起始位置")
    mpdu_zone_start = 7  # ASM(4) + MPDU Header(3)
    epdu_offset = mpdu_zone_start + cadu["first_header_pointer"]
    print(f"  MPDU数据区起始:  字节 {mpdu_zone_start} (ASM 4B + MPDU头 3B)")
    print(f"  首包头指针:      {cadu['first_header_pointer']}")
    print(f"  EPDU包起始位置:  字节 {epdu_offset}")
    print(f"  偏移前填充字节:  {cadu['first_header_pointer']} 字节 (0xAA)")

    # ============================================================
    # 步骤 5: EPDU 主包头解析（6字节）
    # ============================================================
    print_separator("步骤 5: EPDU 主包头解析（6字节）")
    epdu_header = frame[epdu_offset:epdu_offset + 6]
    print(f"  包头原始数据:    {epdu_header.hex(' ').upper()}")

    hdr = parse_epdu_header(epdu_header)
    grouping_map = {0: "中间包", 1: "首包", 2: "末包", 3: "独立包"}
    type_map = {0: "遥测(TM)", 1: "遥控(TC)"}

    print(f"  版本号:          {hdr['version_number']} (0b{hdr['version_number']:03b})")
    print(f"  包类型:          {hdr['packet_type']} → {type_map[hdr['packet_type']]}")
    print(f"  二级头标志:      {hdr['secondary_header_flag']} → {'存在' if hdr['secondary_header_flag'] else '不存在'}")
    print(f"  APID:            0x{hdr['APID']:03X} = {hdr['APID']} → 姿态控制分系统")
    print(f"  分组标志:        {hdr['grouping_flags']} (0b{hdr['grouping_flags']:02b}) → {grouping_map[hdr['grouping_flags']]}")
    print(f"  序列计数:        {hdr['sequence_count']}")
    print(f"  包长字段:        {hdr['packet_data_length']} (0x{hdr['packet_data_length']:04X})")
    print(f"  数据域实际长度:  {hdr['data_field_length']} 字节 (包长+1)")

    # ============================================================
    # 步骤 6: 提取数据域 & CRC 校验
    # ============================================================
    print_separator("步骤 6: 数据域提取 & CRC-CCITT 校验")
    data_field_start = epdu_offset + 6
    data_field = frame[data_field_start:data_field_start + hdr["data_field_length"]]

    # 数据域 = 遥测数据 + CRC(2字节)
    crc_bytes = data_field[-2:]
    crc_received = struct.unpack(">H", crc_bytes)[0]
    telemetry_data = data_field[:-2]

    # CRC 计算范围: 从包头第一个字节到CRC前一个字节
    crc_input = frame[epdu_offset:data_field_start + hdr["data_field_length"] - 2]
    crc_calc = crc_ccitt(crc_input)

    print(f"  数据域起始:      字节 {data_field_start}")
    print(f"  数据域总长度:    {len(data_field)} 字节")
    print(f"  遥测数据长度:    {len(telemetry_data)} 字节")
    print(f"  CRC校验码长度:   2 字节")
    print(f"  遥测数据(HEX):   {telemetry_data.hex(' ').upper()}")
    print(f"  CRC接收值:       0x{crc_received:04X}")
    print(f"  CRC计算值:       0x{crc_calc:04X}")
    print(f"  CRC校验结果:     {'✓ 校验通过' if crc_received == crc_calc else '✗ 校验失败'}")

    # ============================================================
    # 步骤 7: 遥测参数解析（姿态控制系统参数表）
    # ============================================================
    print_separator("步骤 7: 遥测参数解析 — 姿态控制系统")
    print(f"  {'参数名称':<16} {'位置':<10} {'原始值':>8} {'HEX':>6} {'工程值':<24} {'转换公式'}")
    print(f"  {'-'*16} {'-'*10} {'-'*8} {'-'*6} {'-'*24} {'-'*20}")

    params = parse_attitude_telemetry(telemetry_data)
    for p in params:
        print(f"  {p['name']:<16} {p['offset']:<10} {p['raw']:>8} {p['raw_hex']:>6} {p['eng_value']:<24} {p['formula']}")

    # ============================================================
    # 汇总
    # ============================================================
    print_separator("解析汇总")
    print(f"  CADU帧:     256字节, ASM={'✓' if cadu['ASM_valid'] else '✗'}")
    print(f"  MPDU头:     首包头指针={cadu['first_header_pointer']}")
    print(f"  EPDU包头:   APID=0x{hdr['APID']:03X}, 序列={hdr['sequence_count']}, 包长={hdr['packet_data_length']}")
    print(f"  CRC校验:    {'✓ 通过' if crc_received == crc_calc else '✗ 失败'}")
    print(f"  遥测参数:   {len(params)} 个参数解析完成")
    print()


if __name__ == "__main__":
    main()
