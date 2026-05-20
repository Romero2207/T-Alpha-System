import asyncio
import uvicorn
from core.event_bus import SystemEventBus
from engine.data_collector import AsyncDataCollector
from engine.brain_node import BrainNode
import ui.web_server as web_ui


async def run_fastapi():
    # Запускаем Uvicorn (FastAPI) в фоне
    config = uvicorn.Config(web_ui.app, host="127.0.0.1", port=8000, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    print("Инициализация T-Alpha Core...")
    bus = SystemEventBus()

    # Передаем шину событий в веб-сервер
    web_ui.system_bus = bus

    collector = AsyncDataCollector(bus)
    brain = BrainNode(bus)

    bus.subscribe("MARKET_TICK", brain.handle_tick)

    bus_task = asyncio.create_task(bus.run())
    collector_task = asyncio.create_task(collector.run())
    web_task = asyncio.create_task(run_fastapi())

    print("✅ Сервер запущен! Открой в браузере: http://127.0.0.1:8000")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановка системы...")
    finally:
        bus.is_running = False
        collector.is_running = False
        bus_task.cancel()
        collector_task.cancel()
        web_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
