"""Asyncio cancellation registry: one Event per video job, thread-safe."""
import asyncio


class CancellationRegistry:
    def __init__(self) -> None:
        self._events: dict[int, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def request(self, video_id: int) -> None:
        async with self._lock:
            event = self._events.get(video_id)
            if event is None:
                event = asyncio.Event()
                self._events[video_id] = event
            event.set()

    async def is_cancelled(self, video_id: int) -> bool:
        async with self._lock:
            event = self._events.get(video_id)
            return bool(event and event.is_set())

    async def clear(self, video_id: int) -> None:
        async with self._lock:
            self._events.pop(video_id, None)


cancellations = CancellationRegistry()
