import os
import subprocess
import sys


def launch_system():
    print("--- T-ALPHA | INITIALIZING SYSTEM ---")

    # Путь к дашборду
    dashboard_path = os.path.join("ui", "dashboard.py")

    # Команда для запуска streamlit из-под текущего окружения python
    cmd = [sys.executable, "-m", "streamlit", "run", dashboard_path]

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n--- SYSTEM TERMINATED BY USER ---")


if __name__ == "__main__":
    launch_system()