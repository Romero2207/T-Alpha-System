import subprocess
import sys
import time
import os


def start_system():
    print("=" * 50)
    print("Инициализация T-Alpha-System...")
    print("=" * 50)

    # 1. Запуск движка
    print("[1/2] Запуск фонового движка (Core Engine)...")
    collector_script = os.path.join("engine", "data_collector.py")
    subprocess.Popen([sys.executable, collector_script])
    time.sleep(2)

    # 2. Запуск Терминала (Авто-открытие браузера)
    print("[2/2] Запуск Web-Терминала (UI)...")
    terminal_script = os.path.join("ui", "terminal.py")

    # Жесткая привязка к 127.0.0.1 обходит баги Windows с localhost.
    # Браузер откроется сам!
    subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", terminal_script,
        "--server.port", "8501",
        "--server.address", "127.0.0.1",
        "--server.runOnSave", "false",
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false"
    ])

    print("\n✅ СИСТЕМА УСПЕШНО ЗАПУЩЕНА!")
    print("Браузер сейчас откроется автоматически...")
    print("Чтобы остановить бота, нажмите Ctrl+C в этом окне.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановка T-Alpha-System...")


if __name__ == "__main__":
    start_system()