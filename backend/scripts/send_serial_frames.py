"""
RS422 串口模拟设备发送脚本
=========================
模拟一个通过"串口转网络设备"上线的 RS422 传感器节点：

  - 监听 TCP 端口（默认 9123），等待后端串口接收链路（socket://127.0.0.1:9123）连接
  - 连接建立后，按 RS422 自定义帧格式（0xAA 0x55 + 帧长 + 卫星ID + float32 参数 + CRC-16）
    周期性发送遥测帧，演示串口数据接收 -> 组帧 -> 解析 -> 入库/SSE/告警全链路

用法：
  python scripts/send_serial_frames.py                 # 默认 9123 端口发 30 帧
  python scripts/send_serial_frames.py --port 9123 --count 10 --interval 0.5
  python scripts/send_serial_frames.py --count 0        # 一直发送直到 Ctrl+C
"""
import argparse
import socket
import time

from app.protocols import rs422


def build_frame(tick: int, satellite_id: int) -> bytes:
    """构造一帧 RS422 遥测：卫星ID 用可区分的值，参数随 tick 变化。"""
    values = [
        100.0 + tick % 50,
        50.0 + (tick * 2) % 40,
        (tick % 30) * 0.5,
        3.14159 + (tick % 100) / 100.0,
    ]
    return rs422.build_frame(satellite_id=satellite_id, params=values)


def main() -> None:
    parser = argparse.ArgumentParser(description="RS422 串口模拟设备（TCP 监听）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9123)
    parser.add_argument(
        "--satellite-id",
        type=int,
        default=7,
        help="帧内卫星 ID（默认 7，便于与模拟器数据区分）",
    )
    parser.add_argument(
        "--count", type=int, default=30, help="发送帧数，0 表示一直发送"
    )
    parser.add_argument("--interval", type=float, default=1.0, help="帧间隔秒数")
    args = parser.parse_args()

    print(f"[serial-device] 监听 {args.host}:{args.port}，等待后端串口链路连接...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((args.host, args.port))
        srv.listen(1)
        conn, addr = srv.accept()
        print(
            f"[serial-device] 已连接 {addr}，"
            f"开始发送 RS422 帧（satellite_id={args.satellite_id}）"
        )
        with conn:
            tick = 0
            while args.count == 0 or tick < args.count:
                frame = build_frame(tick, args.satellite_id)
                conn.sendall(frame)
                parsed = rs422.parse_frame(frame)
                print(
                    f"  帧 {tick + 1}: {frame.hex(' ').upper()} "
                    f"-> satellite_id={parsed['satellite_id']}, "
                    f"params={[round(v, 3) for v in parsed['params']]}, "
                    f"crc_ok={parsed['crc_ok']}"
                )
                tick += 1
                time.sleep(args.interval)
    print("[serial-device] 发送完成")


if __name__ == "__main__":
    main()
