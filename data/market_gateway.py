import os
import time
from datetime import datetime
import pytz
import requests
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

load_dotenv()

# Настройка временной зоны
MSK = pytz.timezone('Europe/Moscow')


def get_msk_time():
    """Возвращает текущее время в МСК для записи в БД"""
    return datetime.now(MSK).strftime('%Y-%m-%d %H:%M:%S')


class BybitGateway:
    def __init__(self, testnet=False):
        self.client = HTTP(testnet=testnet)
        self.source_name = "BYBIT_MAINNET" if not testnet else "BYBIT_TESTNET"

    def get_ticker(self, symbol):
        start_time = time.perf_counter()
        try:
            response = self.client.get_tickers(category="linear", symbol=symbol)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if response['retCode'] == 0:
                ticker = response['result']['list'][0]
                return {
                    "status": "success",
                    "price": float(ticker['lastPrice']),
                    "volume": float(ticker['volume24h']),
                    "latency_ms": latency_ms,
                    "source": self.source_name,
                    "timestamp": get_msk_time()
                }
            return {"status": "error", "message": response['retMsg']}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class MoexGateway:
    def __init__(self):
        self.source_name = "MOEX_API"

    def get_ticker(self, symbol="SBER"):
        start_time = time.perf_counter()
        try:
            # Прямой запрос к открытому API Мосбиржи (без токенов)
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}.json?iss.meta=off&iss.only=marketdata"
            response = requests.get(url, timeout=5)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if response.status_code == 200:
                data = response.json()
                try:
                    columns = data['marketdata']['columns']
                    row = data['marketdata']['data'][0]
                    market_dict = dict(zip(columns, row))

                    # Если торги закрыты (выходной/ночь), LAST может быть пустым, берем средневзвешенную цену
                    price = market_dict.get('LAST') or market_dict.get('WAPRICE') or 0.0
                    volume = market_dict.get('VALTODAY') or 0.0

                    if price:
                        return {
                            "status": "success",
                            "price": float(price),
                            "volume": float(volume),
                            "latency_ms": latency_ms,
                            "source": self.source_name,
                            "timestamp": get_msk_time()
                        }
                    else:
                        return {"status": "error", "message": "Рынок закрыт / Нет данных о цене"}
                except IndexError:
                    return {"status": "error", "message": "Неверный тикер или пустой ответ"}
            return {"status": "error", "message": f"HTTP Error {response.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}