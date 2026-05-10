import time
import random


class GigaChatInterface:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def get_prediction(self, market_data_context):
        time.sleep(0.3)
        if "No data" in market_data_context:
            return "WAIT: Недостаточно данных для анализа."

        choices = [
            "BUY: Сильный импульс на объемах. Цель +2%.",
            "SELL: Перекупленность по RSI. Ожидаю откат.",
            "HOLD: Низкая волатильность, сигналов нет."
        ]
        return random.choice(choices)