"""
SSE 实时事件总线
===============
基于 asyncio.Queue 的发布-订阅模式，支持线程安全的 SSE 实时推送。
供数据接收流水线推送遥测点、原始帧、告警事件；API 层通过 sse-starlette 消费。

事件类型：
    realtime_point  — 单参数遥测点
    frame           — 整帧数据
    alarm           — 告警事件
"""

import asyncio
import json
import threading
from collections.abc import Callable, AsyncGenerator


class SSEEventBus:
    """基于 asyncio.Queue 的 SSE 发布-订阅事件总线（线程安全）。"""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._lock: threading.Lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置事件循环引用，用于跨线程安全发布。"""
        self._loop = loop

    async def _async_publish(self, event_type: str, data_str: str) -> None:
        """在事件循环内分发给所有订阅者（仅从 _loop 调用）。"""
        msg: tuple[str, str] = (event_type, data_str)
        dead: list[asyncio.Queue] = []
        with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def publish(self, event_type: str, data: dict) -> None:
        """线程安全发布事件。

        可在任意线程调用（asyncio 协程内或后台线程）。
        若事件循环已就绪，通过 call_soon_threadsafe / run_coroutine_threadsafe 投递；
        若尚未设置事件循环，消息将被丢弃（此时无 SSE 订阅者，丢弃是安全的）。
        """
        data_str: str = json.dumps(data, ensure_ascii=False, default=str)
        loop: asyncio.AbstractEventLoop | None = self._loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_publish(event_type, data_str), loop
            )

    def subscribe(self) -> tuple[asyncio.Queue, Callable[[], None]]:
        """订阅 SSE 事件流，返回 (queue, unsubscribe 回调)。

        Returns:
            (asyncio.Queue, Callable): queue 中每个元素为 (event_type, data_str)，
            unsubscribe 调用后取消订阅。
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

        return q, _unsubscribe


# 模块级单例
bus: SSEEventBus = SSEEventBus()


def sse_publish(event_type: str, data: dict) -> None:
    """发布 SSE 事件（线程安全，可在任意线程调用）。

    Args:
        event_type: 事件类型，如 "realtime_point"、"frame"、"alarm"。
        data: 事件载荷，将序列化为 JSON 字符串。
    """
    bus.publish(event_type, data)


def sse_subscribe() -> tuple[asyncio.Queue, Callable[[], None]]:
    """订阅 SSE 事件流。

    Returns:
        (asyncio.Queue, Callable): queue 用于异步取消息，回调用于取消订阅。
    """
    return bus.subscribe()


async def event_stream_generator(
    subscriber_queue: asyncio.Queue,
) -> AsyncGenerator[dict[str, str], None]:
    """SSE 事件流异步生成器。

    供 API 层 sse-starlette 的 EventSourceResponse 使用。
    每次从订阅队列取出一条 (event_type, data_str) 并产出 SSE 格式 dict。

    Args:
        subscriber_queue: 通过 :func:`sse_subscribe` 获得的队列。

    Yields:
        dict: {"event": <event_type>, "data": <data_str>}
    """
    try:
        while True:
            event_type, data_str = await subscriber_queue.get()
            yield {"event": event_type, "data": data_str}
    except asyncio.CancelledError:
        pass
    except GeneratorExit:
        pass
