import asyncio
import time
from typing import Dict, Any
from pybit.unified_trading import HTTP
import requests


class AsyncDataCollector:
    def __init__(self, bus):
        self.bus = bus
        self.bybit = HTTP(testnet=False)
        self.is_running = False
        # Для начала берем узкий пул активов для демо
        self.crypto_symbols = ["BTCUSDT", "ETHUSDT"]
        self.moex_symbols = ["SBER", "LKOH"]

    async def fetch_crypto_tickers(self):
        """Асинхронный опрос криптобиржи (имитация веб-сокетов для старта)"""
        while self.is_running:
            try:
                # В идеале здесь будет WebSocket, но пока делаем частые REST запросы
                res = self.bybit.get_tickers(category="linear")
                if res.get('retCode') == 0:
                    for t in res['result']['list']:
                        if t['symbol'] in self.crypto_symbols:
                            payload = {
                                "symbol": t['symbol'],
                                "price": float(t['lastPrice']),
                                "volume": float(t['turnover24h']),
                                "market": "crypto",
                                "timestamp": time.time()
                            }
                            # Публикуем тик в шину событий
                            await self.bus.publish("MARKET_TICK", payload)
            except Exception as e:
                print(f"[DataCollector] Ошибка Bybit: {e}")

            await asyncio.sleep(2)  # Пауза между опросами

    async def fetch_moex_tickers(self):
        """Асинхронный опрос Мосбиржи"""
        while self.is_running:
            try:
                url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=marketdata"
                # Используем run_in_executor для блокирующего requests
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(None, requests.get, url)

                if res.status_code == 200:
                    data = res.json()['marketdata']['data']
                    cols = res.json()['marketdata']['columns']

                    idx_secid = cols.index('SECID')
                    idx_last = cols.index('LAST')
                    idx_vol = cols.index('VALTODAY')

                    for row in data:
                        symbol = row[idx_secid]
                        if symbol in self.moex_symbols and row[idx_last]:
                            payload = {
                                "symbol": symbol,
                                "price": float(row[idx_last]),
                                "volume": float(row[idx_vol] or 0),
                                "market": "moex",
                                "timestamp": time.time()
                            }
                            await self.bus.publish("MARKET_TICK", payload)
            except Exception as e:
                print(f"[DataCollector] Ошибка MOEX: {e}")

            await asyncio.sleep(5)  # Акции обновляем реже

    async def run(self):
        print("📡 [DataCollector] Запуск потоков данных...")
        self.is_running = True

        # Запускаем сборщики параллельно
        await asyncio.gather(
            self.fetch_crypto_tickers(),
            self.fetch_moex_tickers()
        )