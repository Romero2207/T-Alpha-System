import sys
import os
import time
from datetime import datetime
import requests
from pybit.unified_trading import HTTP

# Подключаем корень проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection, init_db


def load_bybit_history(symbol="BTCUSDT", limit=50):
    print(f"SYSTEM: Downloading Bybit history for {symbol}...")
    client = HTTP(testnet=False)
    try:
        # Запрашиваем 5-минутные свечи
        response = client.get_kline(category="linear", symbol=symbol, interval=5, limit=limit)
        if response['retCode'] == 0:
            klines = response['result']['list']
            # Биржа отдает данные от новых к старым. Переворачиваем, чтобы писать в БД хронологически.
            klines.reverse()

            conn = get_connection()
            cursor = conn.cursor()
            count = 0
            for k in klines:
                # В Bybit API: k[0] = timestamp, k[4] = close price, k[5] = volume
                timestamp = datetime.fromtimestamp(int(k[0]) / 1000).strftime('%Y-%m-%d %H:%M:%S')
                price = float(k[4])
                volume = float(k[5])

                cursor.execute(
                    "INSERT INTO market_data (symbol, price, volume, source, latency_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, price, volume, "BYBIT_HISTORY", 0.0, timestamp)
                )
                count += 1
            conn.commit()
            conn.close()
            print(f"SYSTEM: Successfully loaded {count} historical records for {symbol}.")
    except Exception as e:
        print(f"ERROR: Failed to load Bybit history: {e}")


def load_moex_history(symbol="SBER", limit=50):
    print(f"SYSTEM: Downloading MOEX history for {symbol}...")
    try:
        # Запрашиваем 10-минутные свечи с Мосбиржи
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?iss.meta=off&interval=10"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            candles = data['candles']['data']
            columns = data['candles']['columns']

            # Обрезаем до нужного лимита
            candles = candles[-limit:]

            conn = get_connection()
            cursor = conn.cursor()
            count = 0

            for c in candles:
                # Динамически собираем словарь, чтобы не зависеть от порядка колонок
                candle_dict = dict(zip(columns, c))

                price = float(candle_dict.get('close', 0))
                volume = float(candle_dict.get('volume', 0))
                timestamp = candle_dict.get('end', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

                if price > 0:
                    cursor.execute(
                        "INSERT INTO market_data (symbol, price, volume, source, latency_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                        (symbol, price, volume, "MOEX_HISTORY", 0.0, timestamp)
                    )
                    count += 1

            conn.commit()
            conn.close()
            print(f"SYSTEM: Successfully loaded {count} historical records for {symbol}.")
        else:
            print(f"ERROR: MOEX API returned status {response.status_code}")
    except Exception as e:
        print(f"ERROR: Failed to load MOEX history: {e}")


if __name__ == "__main__":
    # Убеждаемся, что БД существует
    init_db()

    print("-" * 50)
    print("SYSTEM: INITIATING COLD START SEQUENCE")
    print("-" * 50)

    # Загружаем по 50 прошлых свечей (этого хватит для RSI 14 и других базовых индикаторов)
    load_bybit_history("BTCUSDT", limit=50)
    load_moex_history("SBER", limit=50)

    print("-" * 50)
    print("SYSTEM: COLD START COMPLETE. The bot memory is fully operational.")