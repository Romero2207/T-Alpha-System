import time
import sys
import os
import json
import pandas as pd
import ta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection, init_db
from data.market_gateway import BybitGateway, MoexGateway, get_msk_time
from ai.gigachat_api import AIEngine
from engine.risk_manager import RiskManager
from engine.portfolio_manager import PortfolioManager


class DataCollector:
    def __init__(self, interval=20):
        self.interval = interval
        self.ai = AIEngine()
        self.risk_manager = RiskManager()
        self.bybit = BybitGateway(testnet=False)
        self.moex = MoexGateway()
        self.portfolio = PortfolioManager()

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

    def get_rsi(self, symbol, window=14):
        conn = get_connection()
        query = f"SELECT price FROM market_data WHERE symbol='{symbol}' ORDER BY id DESC LIMIT {window + 5}"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) < window:
            return 50.0

        df = df.iloc[::-1].reset_index(drop=True)
        rsi_indicator = ta.momentum.RSIIndicator(close=df['price'], window=window)
        current_rsi = rsi_indicator.rsi().iloc[-1]

        if pd.isna(current_rsi):
            return 50.0
        return round(current_rsi, 2)

    def get_active_assets(self):
        """Динамически читает список активов из БД"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, market_type FROM watchlist")
        rows = cursor.fetchall()
        conn.close()

        assets = []
        for symbol, m_type in rows:
            if m_type == 'crypto':
                assets.append((symbol, self.bybit, symbol))
            else:
                assets.append((symbol, self.moex, symbol))
        return assets
    
    def run(self):
        print(f"SYSTEM: MULTI-ASSET COLLECTOR ONLINE")
        print(f"SYSTEM: DYNAMIC WATCHLIST ACTIVE")
        print("-" * 50)
        while True:
            # Каждый цикл заново читаем список из базы (вдруг ты добавил монету в UI)
            current_assets = self.get_active_assets()

            for identifier, gateway, db_name in current_assets:
                result = gateway.get_ticker(identifier)

                if result["status"] == "success":
                    self.store_data(
                        db_name, result["price"], result["volume"],
                        result["source"], result["latency_ms"], result["timestamp"]
                    )

                    current_rsi = self.get_rsi(db_name)
                    current_state = f"Актив {db_name}. Цена: {result['price']}. RSI: {current_rsi}."

                    # 1. Запрос решения у ИИ (Мозг)
                    decision = self.ai.analyze_market_state(db_name, result["price"], result["volume"], rsi=current_rsi)
                    action = decision.get('action', 'HOLD')
                    confidence = decision.get('confidence', 0)
                    ai_reason = decision.get('reason', 'Нет данных')

                    final_action = action

                    # 2. Проверка через Риск-Менеджмент
                    if action in ["BUY", "SELL"]:
                        approved, rm_reason = self.risk_manager.approve_signal(db_name, action, result['price'],
                                                                               current_rsi)

                        if approved:
                            # ОТПРАВЛЯЕМ В ВИРТУАЛЬНЫЙ КОШЕЛЕК
                            trade_success = self.portfolio.execute_paper_trade(db_name, action, result['price'])
                            if trade_success:
                                print(
                                    f"[{result['timestamp']}] [EXECUTE] {db_name} | {action} | Conf: {confidence}% | Reason: {ai_reason}")
                            else:
                                print(f"[{result['timestamp']}] [INSUFFICIENT FUNDS] {db_name} | {action} blocked")
                        else:
                            print(f"[{result['timestamp']}] [BLOCKED] {db_name} | AI wanted {action} | RM: {rm_reason}")
                            final_action = f"HOLD (Blocked: {action})"
                    # Обновляем решение для записи в память, если оно заблокировано
                    decision['action'] = final_action

                    # 3. Сохранение итогового опыта в БД
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO experience_replay (timestamp, market_state, ai_decision) VALUES (?, ?, ?)",
                        (result["timestamp"], current_state, json.dumps(decision, ensure_ascii=False))
                    )
                    conn.commit()
                    conn.close()

                else:
                    print(f"[{get_msk_time()}] ERROR | {db_name} sync failed: {result.get('message')}")

            print("-" * 50)
            time.sleep(self.interval)


if __name__ == "__main__":
    collector = DataCollector(interval=20)
    collector.run()