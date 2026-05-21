import asyncio
import time
from pybit.unified_trading import HTTP
import requests


class AsyncDataCollector:
    def __init__(self, bus):
        self.bus = bus
        self.bybit = HTTP(testnet=False)
        self.is_running = False
        self.moex_symbols = ["SBER", "LKOH", "GAZP", "YDEX", "T"]
        self.crypto_pool = []  # Теперь это динамический список!

    def update_crypto_pool(self):
        """Умный сканер: отбирает только надежные и ликвидные монеты, отсеивая скам"""
        try:
            print("🔍 [Scanner] Анализ всего рынка Bybit...")
            # Получаем тикеры всего рынка одним запросом!
            res = self.bybit.get_tickers(category="linear")
            if res.get('retCode') == 0:
                valid_coins = []
                for t in res['result']['list']:
                    symbol = t['symbol']

                    # Условия: торгуется к USDT и не является 1000х-шиткоином
                    if symbol.endswith("USDT") and not symbol.startswith("1000"):
                        volume = float(t.get('turnover24h', 0))

                        # 🔥 ЗАЩИТА ОТ СКАМА: Берем только монеты с объемом > $10,000,000 за сутки
                        if volume > 10000000:
                            valid_coins.append(symbol)

                self.crypto_pool = valid_coins
                print(f"✅ [Scanner] В работу взято {len(valid_coins)} самых надежных монет (Объем > $10M).")
        except Exception as e:
            print(f"❌ [Scanner] Ошибка обновления пула: {e}")

    async def fetch_crypto_tickers(self):
        """Асинхронный опрос отобранного пула криптобиржи"""
        self.update_crypto_pool()  # Собираем надежные монеты при старте
        last_pool_update = time.time()

        while self.is_running:
            # Раз в час бот сам перепроверяет рынок и выкидывает мертвые монеты
            if time.time() - last_pool_update > 3600:
                self.update_crypto_pool()
                last_pool_update = time.time()

            try:
                # Получаем актуальные цены ВСЕХ монет одним легким запросом
                res = self.bybit.get_tickers(category="linear")
                if res.get('retCode') == 0:
                    for t in res['result']['list']:
                        # Отправляем в "Мозг" только те монеты, которые прошли фильтр
                        if t['symbol'] in self.crypto_pool:
                            payload = {
                                "symbol": t['symbol'],
                                "price": float(t['lastPrice']),
                                "volume": float(t['turnover24h']),
                                "market": "crypto",
                                "timestamp": time.time()
                            }
                            await self.bus.publish("MARKET_TICK", payload)
            except Exception as e:
                pass

            # Ждем 60 секунд перед новым циклом, чтобы ИИ успевал всё обдумать
            await asyncio.sleep(60)

    async def fetch_moex_tickers(self):
        """Асинхронный опрос Мосбиржи"""
        while self.is_running:
            try:
                url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=marketdata"
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
                pass
            await asyncio.sleep(60)

    async def run(self):
        print("📡 [DataCollector] Запуск потоков данных...")
        self.is_running = True
        await asyncio.gather(self.fetch_crypto_tickers(), self.fetch_moex_tickers())