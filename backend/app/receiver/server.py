"""
真实数据接收服务器（线程版）
============================
基于 socket + threading 的 TCP/UDP 帧接收器：
  - TCP (RECEIVER_PORT=9001)：接收 CCSDS CADU 定长帧（256 字节），面向地面站数据流
  - UDP (RECEIVER_UDP_PORT=9002)：接收 1553B / CAN / RS422 单报文帧（按特征嗅探协议）

收到的帧放入线程安全队列，由 ReceiverManager 的真实接收线程消费：
  帧 → 协议解析 → 参数映射 → 入库(tsdb) + 原始帧入库 + SSE 推送 + 告警检测。

通道启停联动：按协议类型过滤（channel.running=0 时丢弃该协议帧）。
"""
import logging
import queue
import socket
import struct
import threading
import time

from ..config import settings
from ..protocols.rs422 import Rs422Parser

logger: logging.Logger = logging.getLogger(__name__)

CCSDS_FRAME_LEN: int = 256
"""CCSDS CADU 定长帧长度"""


def detect_protocol(data: bytes) -> str | None:
    """UDP 报文协议嗅探（按帧头特征识别）。

    Args:
        data: UDP 报文原始字节。

    Returns:
        str | None: 协议类型（RS422 / CAN / 1553B）或 None。
    """
    if len(data) < 2:
        return None
    # RS422 自定义帧头 0xAA 0x55
    if data[0] == 0xAA and data[1] == 0x55:
        return "RS422"
    # CAN 标准帧：>H arb_id + B dlc + B unused + 数据域（总长 = 4 + dlc）
    if len(data) >= 12:
        arb_id: int = struct.unpack(">H", data[0:2])[0]
        dlc: int = data[2]
        if arb_id <= 0x7FF and dlc <= 8 and 4 + dlc <= len(data) <= 20:
            return "CAN"
    # 1553B：首字为命令字（RT 地址 5bit <= 31）
    if len(data) >= 6:
        cmd: int = struct.unpack(">H", data[0:2])[0]
        rt: int = (cmd >> 11) & 0x1F
        if rt <= 0x1F:
            return "1553B"
    return None


def channel_id_for_protocol(protocol_type: str) -> int:
    """协议类型 → channel_id（复用模拟器加载的通道映射）。"""
    from .simulator import _CCSDS_CH, _M1553B_CH, _CAN_CH, _RS422_CH
    mapping: dict[str, int] = {
        "CCSDS": _CCSDS_CH,
        "1553B": _M1553B_CH,
        "CAN": _CAN_CH,
        "RS422": _RS422_CH,
    }
    return mapping.get(protocol_type, 0)


class RealFrameReceiver:
    """TCP/UDP 真实数据接收器（线程版）。

    帧格式:
        (protocol_type, frame_bytes, channel_id)
    """

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=2000)
        self._running: bool = False
        self._tcp_thread: threading.Thread | None = None
        self._udp_thread: threading.Thread | None = None
        self._serial_thread: threading.Thread | None = None
        self._serial: object | None = None  # pyserial 串口对象（惰性打开）
        self._enabled: dict[str, bool] = {}  # protocol_type -> 是否接收（通道启停联动）

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    @property
    def frame_queue(self) -> queue.Queue:
        """接收到的真实帧队列（元素: (protocol_type, bytes, channel_id)）。"""
        return self._queue

    def set_protocol_enabled(self, protocol_type: str, enabled: bool) -> None:
        """设置某协议通道是否接收（start/stop 接口联动）。"""
        self._enabled[protocol_type] = enabled

    def refresh_enabled_from_db(self) -> None:
        """从数据库 channels 表刷新各协议通道的接收开关。"""
        from ..database import SessionLocal
        from .. import models
        db = SessionLocal()
        try:
            channels = db.query(models.Channel).all()
            for ch in channels:
                if ch.protocol_type:
                    self._enabled[ch.protocol_type] = bool(ch.running)
        finally:
            db.close()

    def start(self) -> None:
        """启动 TCP/UDP 接收线程。"""
        if self._running:
            return
        self._running = True
        self.refresh_enabled_from_db()
        self._tcp_thread = threading.Thread(
            target=self._tcp_loop, daemon=True, name="real-receiver-tcp"
        )
        self._udp_thread = threading.Thread(
            target=self._udp_loop, daemon=True, name="real-receiver-udp"
        )
        self._tcp_thread.start()
        self._udp_thread.start()
        logger.info(
            "真实数据接收已启动 TCP:%d(CCSDS) / UDP:%d(1553B/CAN/RS422)",
            settings.RECEIVER_PORT, settings.RECEIVER_UDP_PORT,
        )
        if settings.RECEIVER_SERIAL_ENABLED:
            self._start_serial()

    def _start_serial(self) -> None:
        """启动串口 RS422 接收（无串口/未装 pyserial 时仅警告，不阻塞启动）。"""
        try:
            import serial  # noqa: F401
        except ImportError:
            logger.warning("pyserial 未安装，串口 RS422 接收不可用")
            return
        port: str = settings.RECEIVER_SERIAL_PORT
        try:
            self._serial = serial.Serial(port, settings.RECEIVER_SERIAL_BAUD, timeout=0.2)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "无法打开串口 %s: %s（可安装虚拟串口 com0com 后启用）", port, e
            )
            return
        self._serial_thread = threading.Thread(
            target=self._serial_loop, daemon=True, name="real-receiver-serial"
        )
        self._serial_thread.start()
        logger.info("串口 RS422 接收已启动 %s @ %d baud", port, settings.RECEIVER_SERIAL_BAUD)

    def _serial_loop(self) -> None:
        """串口循环：逐字节喂 Rs422Parser 状态机组帧，完整帧进入真实接收队列。"""
        parser: Rs422Parser = Rs422Parser()
        while self._running:
            try:
                if self._serial is None:
                    break
                n: int = self._serial.in_waiting
                if n <= 0:
                    time.sleep(0.05)
                    continue
                chunk: bytes = self._serial.read(n)
                for b in chunk:
                    result = parser.feed(b)
                    if result and result.get("raw_bytes"):
                        self._push("RS422", result["raw_bytes"])
            except Exception:  # noqa: BLE001
                logger.exception("串口读取异常")
                time.sleep(1)

    def stop(self) -> None:
        """停止接收线程。"""
        self._running = False
        if self._tcp_thread is not None:
            self._tcp_thread.join(timeout=3.0)
            self._tcp_thread = None
        if self._udp_thread is not None:
            self._udp_thread.join(timeout=3.0)
            self._udp_thread = None
        if self._serial_thread is not None:
            self._serial_thread.join(timeout=3.0)
            self._serial_thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # noqa: BLE001
                pass
            self._serial = None
        logger.info("真实数据接收已停止")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _push(self, protocol_type: str, data: bytes) -> None:
        if not self._running:
            return
        if self._enabled.get(protocol_type, True) is False:
            return  # 该协议通道已停用，丢弃
        try:
            self._queue.put_nowait((protocol_type, data, channel_id_for_protocol(protocol_type)))
        except queue.Full:
            logger.warning("真实帧队列已满，丢弃 %s 帧", protocol_type)

    def _tcp_loop(self) -> None:
        """TCP 监听：CCSDS CADU 定长 256 字节切帧。"""
        srv: socket.socket | None = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((settings.RECEIVER_HOST, settings.RECEIVER_PORT))
            srv.listen(5)
            srv.settimeout(0.5)
            logger.info("TCP 监听中 %s:%d", settings.RECEIVER_HOST, settings.RECEIVER_PORT)
            while self._running:
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                conn.settimeout(0.5)
                logger.info("TCP 客户端已连接 %s", addr)
                buf: bytes = b""
                try:
                    while self._running:
                        try:
                            chunk: bytes = conn.recv(65536)
                        except socket.timeout:
                            continue  # 超时仅作心跳检查，保持连接
                        if not chunk:
                            break
                        buf += chunk
                        # 定长切帧
                        while len(buf) >= CCSDS_FRAME_LEN:
                            frame: bytes = buf[:CCSDS_FRAME_LEN]
                            buf = buf[CCSDS_FRAME_LEN:]
                            self._push("CCSDS", frame)
                except (ConnectionError, OSError):
                    pass
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
                    logger.info("TCP 客户端已断开 %s", addr)
        except OSError as e:
            logger.error("TCP 接收服务启动失败 %s:%d: %s",
                         settings.RECEIVER_HOST, settings.RECEIVER_PORT, e)
        finally:
            if srv is not None:
                try:
                    srv.close()
                except OSError:
                    pass

    def _udp_loop(self) -> None:
        """UDP 监听：单报文一帧，按特征识别协议。"""
        srv: socket.socket | None = None
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            srv.bind((settings.RECEIVER_HOST, settings.RECEIVER_UDP_PORT))
            srv.settimeout(0.5)
            logger.info("UDP 监听中 %s:%d", settings.RECEIVER_HOST, settings.RECEIVER_UDP_PORT)
            while self._running:
                try:
                    data, addr = srv.recvfrom(65536)
                except socket.timeout:
                    continue
                except OSError:
                    break
                proto = detect_protocol(data)
                if proto is None:
                    logger.debug("无法识别 UDP 报文协议，来自 %s", addr)
                    continue
                self._push(proto, data)
        except OSError as e:
            logger.error("UDP 接收服务启动失败 %s:%d: %s",
                         settings.RECEIVER_HOST, settings.RECEIVER_UDP_PORT, e)
        finally:
            if srv is not None:
                try:
                    srv.close()
                except OSError:
                    pass


# 模块级单例 — manager 直接使用
real_receiver: RealFrameReceiver = RealFrameReceiver()
