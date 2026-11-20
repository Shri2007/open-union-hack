"""In-process pub/sub for Server-Sent Events. One set of queues per coalition."""
import asyncio
from collections import defaultdict

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
_loop: asyncio.AbstractEventLoop | None = None


def subscribe(coalition_id: str) -> asyncio.Queue:
    global _loop
    _loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=5000)
    _subscribers[coalition_id].add(q)
    return q


def unsubscribe(coalition_id: str, q: asyncio.Queue) -> None:
    _subscribers[coalition_id].discard(q)


def publish(coalition_id: str, event: str, data: dict) -> None:
    """Safe to call from sync routes running in the threadpool."""
    if _loop is None:
        return
    for q in list(_subscribers.get(coalition_id, ())):
        _loop.call_soon_threadsafe(_put, q, (event, data))


def _put(q: asyncio.Queue, item) -> None:
    if not q.full():  # a stalled screen must never block the relay
        q.put_nowait(item)
