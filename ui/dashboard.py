import sqlite3
from datetime import datetime
import pandas as pd

class AlphaMemory:
    def __init__(self, db_path="data/alpha_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Таблица сделок и решений ИИ
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    symbol TEXT,
                    market_type TEXT,
                    action TEXT,
                    price REAL,
                    ai_confidence REAL,
                    reasoning TEXT,
                    result REAL DEFAULT 0
                )
            """)
            # Таблица для "обучения" - храним паттерны
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    pattern_data TEXT,
                    outcome TEXT
                )
            """)
            conn.commit()

    def save_decision(self, symbol, m_type, action, price, confidence, reasoning):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_history (timestamp, symbol, market_type, action, price, ai_confidence, reasoning)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (datetime.now(), symbol, m_type, action, price, confidence, reasoning))
            conn.commit()

    def get_history(self, limit=50):
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query(f"SELECT * FROM trade_history ORDER BY timestamp DESC LIMIT {limit}", conn)

    def get_stats(self):
        # Здесь будет логика для обучения: сколько раз ИИ угадал движение
        pass