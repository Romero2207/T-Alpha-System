import asyncio
from typing import Dict, Any


# Сюда позже импортируем наш ai/gigachat_api.py и risk_manager.py

class BrainNode:
    def __init__(self, bus):
        self.bus = bus
        self.last_analysis_time = {}

    async def handle_tick(self, payload: Dict[str, Any]):
        """Обработчик события MARKET_TICK"""
        symbol = payload['symbol']
        price = payload['price']

        # Чтобы не спамить нейросеть каждую секунду, анализируем актив раз в 60 секунд
        current_time = payload['timestamp']
        last_time = self.last_analysis_time.get(symbol, 0)

        if current_time - last_time >= 60:
            print(f"🧠 [Brain] Анализ {symbol} по цене {price}...")
            self.last_analysis_time[symbol] = current_time

            # TODO: Здесь мы будем вызывать AIEngine и RiskManager
            # Имитация работы ИИ (задержка 2 секунды)
            await asyncio.sleep(2)

            # Имитация сигнала
            signal = {
                "symbol": symbol,
                "action": "BUY" if price % 2 == 0 else "HOLD",  # Заглушка
                "price": price,
                "confidence": 85
            }

            if signal["action"] != "HOLD":
                print(f"⚡ [Brain] Сгенерирован сигнал: {signal['action']} {symbol}")
                await self.bus.publish("TRADE_SIGNAL", signal)