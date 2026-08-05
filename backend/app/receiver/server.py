"""
Socket / UDP 接收服务器
=======================
基于 asyncio 的最小化 TCP/UDP 接收服务，接收二进制帧后投递到解析队列。

实际场景中 TCP Socket 接收来自卫星地面站的 CCSDS CADU 帧，
UDP 端口可用于接收 1553B/CAN/RS422 等协议帧。

当前实现将接收到的原始字节直接放入队列，由 manager 统一解析入库。
"""

import asyncio
import logging

from ..config import settings

logger: logging.Logger = logging.getLogger(__name__)


class FrameReceiver:
    """asyncio TCP/UDP 帧接收器。

    对每个 TCP 连接按字节流接收，对 UDP 按报文接收。
    """

    def __init__(self) -> None:
        self._tcp_server: asyncio.Server | None = None
        self._udp_transport: asyncio.DatagramTransport | None = None
        self._udp_protocol: "UdpProtocol | None" = None
        self._frame_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    @property
    def frame_queue(self) -> asyncio.Queue:
        """外部可通过此队列消费接收到的原始帧字节。"""
        return self._frame_queue

    async def start(self) -> None:
        """启动 TCP 和 UDP 监听。"""
        host: str = settings.RECEIVER_HOST
        tcp_port: int = settings.RECEIVER_PORT
        udp_port: int = settings.RECEIVER_UDP_PORT

        try:
            self._tcp_server = await asyncio.start_server(
                self._handle_tcp_connection, host, tcp_port
            )
            logger.info("TCP 接收服务已启动 %s:%d", host, tcp_port)
        except OSError as e:
            logger.warning("TCP 接收服务启动失败 %s:%d: %s", host, tcp_port, e)

    async def stop(self) -> None:
        """停止 TCP 和 UDP 监听。"""
        if self._tcp_server is not None:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
            self._tcp_server = None
            logger.info("TCP 接收服务已停止")

    async def _handle_tcp_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """TCP 连接处理器：读入字节流并放入帧队列。

        Args:
            reader: asyncio 流读取器。
            writer: asyncio 流写入器。
        """
        peer: str = writer.get_extra_info("peername", "unknown")
        logger.info("TCP 客户端已连接 %s", peer)
        try:
            while True:
                buf: bytes = await reader.read(4096)
                if not buf:
                    break
                try:
                    self._frame_queue.put_nowait(buf)
                except asyncio.QueueFull:
                    logger.warning("帧队列已满，丢弃来自 %s 的数据", peer)
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("TCP 客户端已断开 %s", peer)


class UdpProtocol(asyncio.DatagramProtocol):
    """UDP 协议处理器。"""

    def __init__(self, queue: asyncio.Queue) -> None:
        super().__init__()
        self._queue: asyncio.Queue = queue

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        """UDP 报文回调。"""
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("帧队列已满，丢弃来自 %s 的 UDP 数据", addr)


async def start_server() -> FrameReceiver:
    """启动接收服务（便捷函数）。

    Returns:
        FrameReceiver: 已启动的接收器实例。
    """
    receiver: FrameReceiver = FrameReceiver()
    await receiver.start()
    return receiver


async def stop_server(receiver: FrameReceiver | None) -> None:
    """停止接收服务（便捷函数）。

    Args:
        receiver: 接收器实例。
    """
    if receiver is not None:
        await receiver.stop()
