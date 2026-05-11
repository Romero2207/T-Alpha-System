import time


class RiskManager:
    def __init__(self):
        # Память о времени последних сделок для каждого актива
        self.last_trade_time = {}
        # Cooldown: 300 секунд (5 минут) блокировки после любого торгового сигнала
        self.cooldown_seconds = 300

    def approve_signal(self, symbol, action, price, rsi):
        """
        Проверяет сигнал ИИ через жесткие математические фильтры.
        Возвращает (Одобрено: bool, Причина_блокировки: str)
        """
        if action not in ["BUY", "SELL"]:
            return False, "Neutral signal"

        # 1. Проверка Cooldown (Дисциплина алгоритма)
        current_time = time.time()
        if symbol in self.last_trade_time:
            time_since_last = current_time - self.last_trade_time[symbol]
            if time_since_last < self.cooldown_seconds:
                wait_time = int(self.cooldown_seconds - time_since_last)
                return False, f"COOLDOWN ACTIVE ({wait_time}s remaining)"

        # 2. Математический фильтр RSI (Защита от галлюцинаций ИИ)
        if action == "BUY" and rsi > 70:
            return False, f"BLOCKED: Attempt to BUY on overbought market (RSI {rsi} > 70)"

        if action == "SELL" and rsi < 30:
            return False, f"BLOCKED: Attempt to SELL on oversold market (RSI {rsi} < 30)"

        # Если сигнал прошел все круги проверки:
        self.last_trade_time[symbol] = current_time
        return True, "APPROVED BY RISK MANAGER"