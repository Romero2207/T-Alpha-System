import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Ключи API
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
T_INVEST_TOKEN = os.getenv("T_INVEST_TOKEN")

# Доступы к GUI
GUI_USERNAME = os.getenv("GUI_USERNAME", "admin")
GUI_PASSWORD = os.getenv("GUI_PASSWORD", "admin")

# Настройки рынка
DEFAULT_SYMBOL = "BTCUSDT"
T_SBER_FIGI = "BBG004730N88" # FIGI Сбера