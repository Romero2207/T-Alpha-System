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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            price REAL,
            volume REAL,
            source TEXT,
            latency_ms REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experience_replay (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            market_state TEXT,
            ai_decision TEXT,
            result_after_n_min REAL
        )
    ''')
    conn.commit()
    conn.close()


# --- VECTOR MEMORY (Смыслы и Паттерны) ---
def get_vector_db():
    """Инициализация и получение доступа к векторной памяти ИИ"""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # Создаем коллекцию (таблицу) для рыночных паттернов
    collection = client.get_or_create_collection(name="market_patterns")
    return collection


if __name__ == "__main__":
    init_db()
    # Проверка создания векторной базы
    v_db = get_vector_db()
    print("SYSTEM: Relational DB (SQLite) initialized.")
    print(f"SYSTEM: Vector Memory (ChromaDB) initialized. Patterns count: {v_db.count()}")