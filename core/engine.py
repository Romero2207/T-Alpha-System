from ai.gigachat_api import analyze_market_context
from core.risk_manager import calculate_position_size


class TradingEngine:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol

    def process_cycle(self, price, news, risk_params):
        """Полный цикл анализа ситуации"""
        # 1. Запрос к ИИ
        score, ai_comment = analyze_market_context(news)

        # 2. Определение направления
        decision = "ОЖИДАНИЕ"
        size = 0

        if score >= 6:
            decision = "ПОКУПКА"
            # Стоп-лосс на 1% ниже текущей цены
            sl = price * 0.99
            size = calculate_position_size(risk_params['depo'], risk_params['risk'], price, sl)

        elif score <= -6:
            decision = "ПРОДАЖА"
            sl = price * 1.01
            size = calculate_position_size(risk_params['depo'], risk_params['risk'], price, sl)

        return {
            "action": decision,
            "size": size,
            "score": score,
            "reason": ai_comment
        }