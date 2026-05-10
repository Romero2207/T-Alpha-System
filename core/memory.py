import sqlite3
import pandas as pd
from datetime import datetime
import os

class AlphaMemory:
    def __init__(self, db_name="data/alpha_vault.db"):
        os.makedirs("data", exist_ok=True)
        self.db_name = db_name
        self._init_tables()

    def _init_tables(self):
        """Создаем таблицы, если их нет. Память должна быть вечной."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Таблица котировок (для обучения ML)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_data (
                    timestamp DATETIME,
                    symbol TEXT,
                    price REAL,
                    volume REAL,
                    market_type TEXT
                )
            """)
            # Таблица логов ИИ (опыт и рассуждения)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_logic_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    symbol TEXT,
                    decision TEXT,
                    confidence REAL,
                    context_snapshot TEXT,
                    result_success INTEGER DEFAULT NULL
                )
            """)
            conn.commit()

    def save_market_tick(self, symbol, price, volume, m_type):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("INSERT INTO market_data VALUES (?, ?, ?, ?, ?)",
                         (datetime.now(), symbol, price, volume, m_type))

    def log_ai_decision(self, symbol, decision, confidence, context):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute("INSERT INTO ai_logic_logs (timestamp, symbol, decision, confidence, context_snapshot) VALUES (?, ?, ?, ?, ?)",
                         (datetime.now(), symbol, decision, confidence, str(context)))

    def get_last_prices(self, symbol, limit=100):
        with sqlite3.connect(self.db_name) as conn:
            query = f"SELECT * FROM market_data WHERE symbol = '{symbol}' ORDER BY timestamp DESC LIMIT {limit}"
            return pd.read_sql_query(query, conn)