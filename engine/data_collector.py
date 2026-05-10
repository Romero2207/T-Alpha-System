import time
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection, init_db
from data.market_gateway import BybitGateway, MoexGateway, get_msk_time
from ai.gigachat_api import AIEngine


class DataCollector:
    def __init__(self, interval=20):
        self.interval = interval
        self.ai = AIEngine()
        # Инициализируем рабочие шлюзы
        self.bybit = BybitGateway(testnet=False)
        self.moex = MoexGateway()

        # Список инструментов: (символ, шлюз, имя для БД)
        self.assets = [
            ("BTCUSDT", self.bybit, "BTCUSDT"),
            ("SBER", self.moex, "SBER")
        ]
        init_db()

    def store_data(self, symbol, price, volume, source, latency_ms, timestamp):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO market_data (symbol, price, volume, source, latency_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, price, volume, source, latency_ms, timestamp)
        )
        conn.commit()
        conn.close()

    def run(self):
        print(f"SYSTEM: MULTI-ASSET COLLECTOR ONLINE (MSK TIME)")
        print("-" * 50)
        while True:
            for identifier, gateway, db_name in self.assets:
                result = gateway.get_ticker(identifier)

                if result["status"] == "success":
                    self.store_data(
                        db_name, result["price"], result["volume"],
                        result["source"], result["latency_ms"], result["timestamp"]
                    )

                    # Анализ состояния
                    current_state = f"Актив {db_name}. Текущая цена: {result['price']}."
                    decision = self.ai.analyze_market_state(db_name, result["price"], result["volume"])

                    # Сохранение в опыт
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO experience_replay (timestamp, market_state, ai_decision) VALUES (?, ?, ?)",
                        (result["timestamp"], f"{db_name} | {current_state}", json.dumps(decision, ensure_ascii=False))
                    )
                    conn.commit()
                    conn.close()

                    print(f"[{result['timestamp']}] {db_name} | P: {result['price']} | AI: {decision.get('action')}")
                else:
                    print(f"[{get_msk_time()}] ERROR | {db_name} sync failed: {result.get('message')}")

            print("-" * 50)
            time.sleep(self.interval)


if __name__ == "__main__":
    collector = DataCollector(interval=30)
    collector.run()