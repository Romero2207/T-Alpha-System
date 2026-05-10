import time
import sys
import os
from pybit.unified_trading import HTTP

# Добавляем корневую директорию в PYTHONPATH для корректных импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection, init_db

class DataCollector:
    def __init__(self, symbol="BTCUSDT", interval=5):
        self.symbol = symbol
        self.interval = interval # Интервал сбора данных в секундах
        # Инициализируем клиент Bybit Testnet
        self.client = HTTP(testnet=True)
        init_db() # Убеждаемся, что БД существует

    def fetch_and_store(self):
        try:
            response = self.client.get_tickers(category="linear", symbol=self.symbol)
            if response['retCode'] == 0:
                ticker = response['result']['list'][0]
                price = float(ticker['lastPrice'])
                volume = float(ticker['volume24h'])

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO market_data (symbol, price, volume, source) VALUES (?, ?, ?, ?)",
                    (self.symbol, price, volume, "BYBIT_TESTNET")
                )
                conn.commit()
                conn.close()
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Saved {self.symbol} | Price: {price} | Vol: {volume}")
        except Exception as e:
            print(f"Error fetching data: {e}")

    def run(self):
        print(f"Starting T-Alpha Data Collector for {self.symbol}...")
        while True:
            self.fetch_and_store()
            time.sleep(self.interval)

if __name__ == "__main__":
    # Запуск фонового демона
    collector = DataCollector(symbol="BTCUSDT", interval=10)
    collector.run()