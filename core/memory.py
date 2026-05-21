import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "t_alpha.db")
CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")


def get_connection():
    # Подключаемся (если файла нет, он создастся сам)
    conn = sqlite3.connect("trading_bot.db", timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  # Турбо-режим

    # БРОНЕБОЙНАЯ ЗАЩИТА: Автоматически создаем все таблицы, если их кто-то удалил
    conn.execute('''CREATE TABLE IF NOT EXISTS portfolio (
                        symbol TEXT UNIQUE, 
                        amount REAL, 
                        average_entry_price REAL)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS trade_history (
                        timestamp TEXT, 
                        symbol TEXT, 
                        action TEXT, 
                        price REAL, 
                        amount REAL, 
                        total_value REAL)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS experience_replay (
                        timestamp TEXT, 
                        market_state TEXT, 
                        ai_decision TEXT)''')
    conn.commit()

    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, market_type TEXT)''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            symbol TEXT PRIMARY KEY, 
            amount REAL, 
            average_entry_price REAL DEFAULT 0.0,
            take_profit REAL DEFAULT 0.0,
            stop_loss REAL DEFAULT 0.0,
            high_water_mark REAL DEFAULT 0.0
        )
    ''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS trade_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                        symbol TEXT, action TEXT, price REAL, amount REAL, total_value REAL, reason TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS market_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        symbol TEXT, price REAL, volume REAL, source TEXT, latency_ms REAL, timestamp DATETIME)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS experience_replay (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, market_state TEXT, ai_decision TEXT)''')

    cursor.execute("SELECT count(*) FROM portfolio WHERE symbol='USDT'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO portfolio (symbol, amount) VALUES ('USDT', 1000.0)")
        cursor.execute("INSERT INTO portfolio (symbol, amount) VALUES ('RUB', 50000.0)")

    conn.commit()
    conn.close()


class DummyVectorDB:
    def similarity_search(self, query, k=3): return []

    def as_retriever(self): return self

    def get_relevant_documents(self, query): return []


def get_vector_db():
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        return client.get_or_create_collection(name="market_patterns")
    except Exception:
        return DummyVectorDB()


if __name__ == "__main__":
    init_db()
    print("SYSTEM: Relational DB (SQLite) fully initialized with all tables.")