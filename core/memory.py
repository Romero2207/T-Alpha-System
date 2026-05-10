import sqlite3
import os

# База данных будет создана в корне проекта
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "t_alpha.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица для сырых рыночных данных (тиков)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            price REAL,
            volume REAL,
            source TEXT
        )
    ''')

    # Таблица Experience Replay для самообучения
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


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")