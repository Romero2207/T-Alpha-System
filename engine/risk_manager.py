import time
from datetime import datetime


class RiskManager:
    def __init__(self):
        self.last_trade_time = {}
        self.cooldown_seconds = 300

        # Интегрированный календарь важных событий (Май 2026)
        # Если до события менее 3 дней, входить в позицию в режиме Low Risk запрещено
        self.events_calendar = {
            "SBER": {"date": "2026-05-20", "type": "Дивидендная отсечка"},
            "LKOH": {"date": "2026-05-22", "type": "Финансовый отчет МСФО"},
            "GAZP": {"date": "2026-05-25", "type": "Совет Директоров"},
            "YDEX": {"date": "2026-05-28", "type": "Собрание акционеров"}
        }

    def approve_signal(self, symbol, action, price, rsi, news_sentiment=0.0, risk_profile="Medium"):
        """
        Проверяет сигнал ИИ через технические, событийные и новостные фильтры.
        news_sentiment: от -1.0 (паника) до +1.0 (эйфория).
        """
        if action not in ["BUY", "SELL"]:
            return False, "Neutral signal"

        current_time = time.time()

        # 1. Проверка Cooldown (Дисциплина тайминга)
        if symbol in self.last_trade_time:
            time_since_last = current_time - self.last_trade_time[symbol]
            if time_since_last < self.cooldown_seconds:
                wait_time = int(self.cooldown_seconds - time_since_last)
                return False, f"COOLDOWN ACTIVE ({wait_time}s remaining)"

        # 2. Технический фильтр RSI (Защита от покупок на хаях)
        if action == "BUY" and rsi > 70:
            return False, f"BLOCKED BY RSI: Attempt to BUY on overbought market (RSI {rsi} > 70)"
        if action == "SELL" and rsi < 30:
            return False, f"BLOCKED BY RSI: Attempt to SELL on oversold market (RSI {rsi} < 30)"

        # 3. ИИ-Новостной фильтр (Защита от негативного инсайда)
        if action == "BUY" and news_sentiment < -0.35:
            return False, f"BLOCKED BY NEWS SENTIMENT: Negative market environment ({news_sentiment:.2f})"

        # 4. Событийный календарный фильтр (Режим консервативного Low-Risk трейдинга)
        if risk_profile == "Low" and symbol in self.events_calendar:
            try:
                event_date = datetime.strptime(self.events_calendar[symbol]["date"], "%Y-%m-%d").date()
                current_date = datetime.now().date()
                days_to_event = (event_date - current_date).days

                if 0 <= days_to_event <= 3:
                    event_type = self.events_calendar[symbol]["type"]
                    return False, f"BLOCKED BY CALENDAR: Close to critical event '{event_type}' on {event_date} ({days_to_event} days left)"
            except Exception as e:
                print(f"Ошибка проверки календаря для {symbol}: {e}")

        # Сигнал прошел все уровни валидации
        self.last_trade_time[symbol] = current_time
        return True, "APPROVED BY RISK MANAGER"