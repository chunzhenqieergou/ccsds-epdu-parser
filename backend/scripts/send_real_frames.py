# -*- coding: utf-8 -*-
"""
真实数据发送测试脚本
====================
向 STMS 真实接收端口发送四类协议帧，验证「真实接收 → 协议解析 → 入库 → 实时展示」链路：

  - TCP   :9001  → CCSDS CADU 定长帧（256 字节）
  - UDP   :9002  → 1553B / CAN / RS422 单报文帧

帧由模拟器模块的帧构建函数生成（与后端解析逻辑对称），无需启动模拟器。

用法:
  python scripts/send_real_frames.py                # 每类发 10 帧，间隔 1s
  python scripts/send_real_frames.py --count 5 --interval 2
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.config import settings  # noqa: E402
from app.receiver.simulator import (  # noqa: E402
    _build_ccsds_frame,
    _build_m1553b_frame,
    _build_can_frame,
    _build_rs422_frame,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="向 STMS 发送真实协议帧")
    parser.add_argument("--count", type=int, default=10, help="每类协议发送帧数")
    parser.add_argument("--interval", type=float, default=1.0, help="发送间隔（秒）")
    args = parser.parse_args()

    tcp: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.settimeout(5)
    tcp.connect((settings.RECEIVER_HOST, settings.RECEIVER_PORT))
    print(f"[TCP] 已连接 {settings.RECEIVER_HOST}:{settings.RECEIVER_PORT}")

    udp: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_addr = (settings.RECEIVER_HOST, settings.RECEIVER_UDP_PORT)
    print(f"[UDP] 目标 {settings.RECEIVER_HOST}:{settings.RECEIVER_UDP_PORT}")

    builders = [
        (_build_m1553b_frame, "1553B"),
        (_build_can_frame, "CAN"),
        (_build_rs422_frame, "RS422"),
    ]

    for tick in range(args.count):
        # CCSDS CADU → TCP
        fr = _build_ccsds_frame(tick, [])
        tcp.sendall(fr["frame_bytes"])
        print(f"[{tick:02d}] TCP → CCSDS   {len(fr['frame_bytes'])} 字节")

        # 1553B / CAN / RS422 → UDP
        for builder, name in builders:
            f2 = builder(tick, [])
            udp.sendto(f2["frame_bytes"], udp_addr)
            print(f"[{tick:02d}] UDP → {name:<5} {len(f2['frame_bytes'])} 字节")

        if args.interval > 0 and tick < args.count - 1:
            time.sleep(args.interval)

    tcp.close()
    udp.close()
    print("发送完成")


if __name__ == "__main__":
    main()
