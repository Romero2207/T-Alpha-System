import subprocess
import sys
import time
import os


def start_system():
    print("=" * 50)
    print("ВОССТАНОВЛЕНИЕ T-ALPHA PRO...")
    print("=" * 50)

    # 1. Движок
    collector_script = os.path.join("engine", "data_collector.py")
    subprocess.Popen([sys.executable, collector_script])

    time.sleep(2)

    # 2. Терминал (Стабильный режим)
    terminal_script = os.path.join("ui", "terminal.py")
    subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", terminal_script,
        "--server.runOnSave", "false",
        "--server.fileWatcherType", "none",
        "--server.address", "127.0.0.1"
    ])

    print("\n✅ СИСТЕМА ЗАПУЩЕНА! Откройте http://127.0.0.1:8501")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\nВыключение...")


if __name__ == "__main__":
    start_system()