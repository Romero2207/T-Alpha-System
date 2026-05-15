import sqlite3
import os
import chromadb

# Пути к базам данных
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "t_alpha.db")
CHROMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")


# --- SQLITE MEMORY (Цифры и Котировки) ---
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Таблица отслеживаемых инструментов
    cursor.execute('''CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, market_type TEXT)''')

    # 2. Таблица кошелька (Портфель) - ВАЖНО: ДОБАВЛЕНЫ СТОПЫ И ТРЕЙЛИНГ
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

    # 3. Таблица истории сделок
    cursor.execute('''CREATE TABLE IF NOT EXISTS trade_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
                        symbol TEXT, action TEXT, price REAL, amount REAL, total_value REAL, reason TEXT)''')

    # 4. Таблица сырых рыночных данных
    cursor.execute('''CREATE TABLE IF NOT EXISTS market_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        symbol TEXT, price REAL, volume REAL, source TEXT, latency_ms REAL, timestamp DATETIME)''')

    # 5. Таблица логов ИИ
    cursor.execute('''CREATE TABLE IF NOT EXISTS experience_replay (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        timestamp DATETIME, market_state TEXT, ai_decision TEXT)''')

    # Базовые активы по умолчанию
    cursor.execute("SELECT count(*) FROM watchlist")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO watchlist (symbol, market_type) VALUES ('BTCUSDT', 'crypto')")
        cursor.execute("INSERT INTO watchlist (symbol, market_type) VALUES ('SBER', 'stocks')")

    conn.commit()
    conn.close()


# --- VECTOR MEMORY (Смыслы и Паттерны) ---
def get_vector_db():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="market_patterns")
    return collection


if __name__ == "__main__":
    init_db()
    v_db = get_vector_db()
    print("SYSTEM: Relational DB (SQLite) fully initialized with all tables.")
    print(f"SYSTEM: Vector Memory (ChromaDB) initialized. Patterns count: {v_db.count()}")