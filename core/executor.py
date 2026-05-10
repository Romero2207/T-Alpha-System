import time
import pandas as pd


class TradeExecutor:
    def __init__(self, initial_balance=1000.0):
        self.balance = initial_balance
        self.history = []
        self.positions = []

    def open_trade(self, action, symbol, price, size, reason):
        """Регистрация сделки в журнале"""
        if size <= 0: return None

        trade = {
            "ID": len(self.history) + 1,
            "Время": time.strftime("%H:%M:%S"),
            "Инструмент": symbol,
            "Операция": action,
            "Цена входа": f"{price:.2f}",
            "Объем": size,
            "Результат": "В процессе",
            "Анализ": reason[:50] + "..."
        }

        self.history.append(trade)
        # Симуляция изменения баланса (комиссия 0.1%)
        cost = price * size * 0.001
        self.balance -= cost
        return trade

    def get_history_dataframe(self):
        if not self.history:
            return pd.DataFrame(columns=["Время", "Инструмент", "Операция", "Цена входа", "Объем", "Анализ"])
        return pd.DataFrame(self.history)