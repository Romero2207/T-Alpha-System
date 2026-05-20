import asyncio
from typing import Dict, Any, Callable, Awaitable


class SystemEventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._subscribers: Dict[str, list[Callable[[Dict[str, Any]], Awaitable[None]]]] = {}
        self.is_running: bool = False

    def subscribe(self, event_type: str, handler: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Подписка на определенный тип событий (например, 'MARKET_TICK' или 'AI_SIGNAL')"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Асинхронная публикация события в очередь"""
        await self._queue.put({"type": event_type, "data": payload})

    async def run(self) -> None:
        """Асинхронный воркер обработки маршрутизации событий"""
        self.is_running = True
        while self.is_running:
            event = await self._queue.get()
            event_type = event["type"]

            if event_type in self._subscribers:
                for handler in self._subscribers[event_type]:
                    # Запускаем обработчики как независимые таски, чтобы не блокировать шину
                    asyncio.create_task(handler(event["data"]))

            self._queue.task_done()