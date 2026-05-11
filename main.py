import subprocess
import sys
import time


def start_system():
    print("=" * 50)
    print("Инициализация T-Alpha-System...")
    print("=" * 50)

    # 1. Запуск движка (Сборщик данных и ИИ)
    print("[1/2] Запуск фонового движка (Core Engine)...")
    engine_process = subprocess.Popen([sys.executable, "engine/data_collector.py"])
    time.sleep(3)  # Ждем 3 секунды, чтобы база данных успела открыться

    # 2. Запуск браузера (Визуальный терминал Streamlit)
    print("[2/2] Запуск Web-Терминала (UI)...")
    ui_process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "ui/terminal.py"])

    print("\n✅ СИСТЕМА УСПЕШНО ЗАПУЩЕНА!")
    print("Чтобы остановить бота, нажмите Ctrl+C в этом окне.")

    # Оставляем скрипт работать и следить за процессами
    try:
        engine_process.wait()
        ui_process.wait()
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал на остановку...")
        engine_process.terminate()
        ui_process.terminate()
        print("T-Alpha-System выключена. До встречи.")


if __name__ == "__main__":
    start_system()