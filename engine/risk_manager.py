import json
import os
import sys
import pandas as pd

# Подключаем доступ к базе данных
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection


class RiskManager:
    def __init__(self):
        self.crypto_mode = "low"
        self.moex_mode = "low"
        self.settings_file = "settings.json"

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    self.crypto_mode = data.get("crypto", "low")
                    self.moex_mode = data.get("moex", "low")
        except:
            pass

    def check_open_position(self, symbol):
        """Проверяем, есть ли уже этот актив в нашем портфеле"""
        try:
            conn = get_connection()
            # Ищем актив с положительным балансом
            df = pd.read_sql_query(f"SELECT amount FROM portfolio WHERE symbol='{symbol}' AND amount > 0", conn)
            conn.close()
            return not df.empty
        except:
            return False

    def approve_signal(self, symbol, action, price, inds):
        self.load_settings()
        mode = self.crypto_mode if "USDT" in symbol else self.moex_mode

        rsi = inds.get('rsi', 50)
        atr = inds.get('atr') if inds.get('atr') and inds.get('atr') > 0 else (price * 0.01)

        sl_mult = 2.0 if mode == "medium" else 1.5
        rr_ratio = 2.5 if mode == "medium" else 2.0

        sl_price, tp_price = 0.0, 0.0

        # Узнаем, куплена ли уже бумага
        has_position = self.check_open_position(symbol)

        if action == "BUY":
            # УМНАЯ ЛОГИКА: Не покупаем, если уже есть в портфеле
            if has_position:
                return False, f"БЛОК: Актив {symbol} уже куплен. Ждем профита.", 0, 0

            max_rsi = 75 if mode == "medium" else 65
            if rsi > max_rsi:
                return False, f"БЛОК: RSI={rsi} перегрет (Режим: {mode.upper()})", 0, 0

            sl_price = price - (atr * sl_mult)
            tp_price = price + (atr * sl_mult * rr_ratio)

        elif action == "SELL":
            # УМНАЯ ЛОГИКА: Не продаем то, чего у нас нет
            if not has_position:
                return False, f"БЛОК: Нет актива {symbol} в портфеле для продажи.", 0, 0

            min_rsi = 25 if mode == "medium" else 35
            if rsi < min_rsi:
                return False, f"БЛОК: RSI={rsi} перепродан (Режим: {mode.upper()})", 0, 0

            sl_price = price + (atr * sl_mult)
            tp_price = price - (atr * sl_mult * rr_ratio)

        return True, f"Одобрено. Risk/Reward 1:{rr_ratio}", round(sl_price, 4), round(tp_price, 4)