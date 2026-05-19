import os
import json
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_vector_db
from gigachat import GigaChat

load_dotenv()


class AIEngine:
    def __init__(self):
        self.credentials = os.getenv("GIGACHAT_CREDENTIALS", "")
        self.v_db = get_vector_db()

    def analyze_market_state(self, symbol, current_price, current_volume, indicators):
        # Базовые индикаторы
        rsi = indicators.get('rsi', 50.0)
        macd = indicators.get('macd_hist', 0.0)
        atr = indicators.get('atr', 0.0)
        pattern = indicators.get('pattern', 'Нет явного паттерна')

        # Расширенные метрики (Ликвидность и Гэпы)
        local_high = indicators.get('local_high', current_price * 1.05)
        local_low = indicators.get('local_low', current_price * 0.95)
        gap_percent = indicators.get('gap_percent', 0.0)
        market_type = indicators.get('market_type', 'crypto')

        # Интеграция новостей и макро-трендов
        news_sentiment = indicators.get('news_sentiment', 0.0)
        news_feed = indicators.get('news_feed', 'Без новостей.')
        sma200 = indicators.get('sma200', 0.0)

        macro_trend = "БЫЧИЙ" if current_price > sma200 and sma200 > 0 else "МЕДВЕЖИЙ"

        current_state = (
            f"Актив: {symbol} (Рынок: {market_type.upper()}). Цена: {current_price}.\n"
            f"--- АНАЛИЗ ЛИКВИДНОСТИ: ---\n"
            f"• Зона сопротивления (Локальный Хай): {local_high}\n"
            f"• Зона поддержки (Локальный Лой): {local_low}\n"
            f"• Ценовой разрыв (Gap): {gap_percent}%\n"
            f"--- ТЕХНИКА И СЕНТИМЕНТ: ---\n"
            f"• RSI: {rsi} | MACD: {macd} | Паттерн: {pattern}\n"
            f"• Тренд (SMA200): {macro_trend}\n"
            f"• Новости ({news_sentiment}): {news_feed}"
        )

        try:
            similar_patterns = self.v_db.query(query_texts=[current_state], n_results=1)
            memory_context = "Прошлый опыт: " + " | ".join(similar_patterns['documents'][0]) if similar_patterns[
                                                                                                    'documents'] and \
                                                                                                similar_patterns[
                                                                                                    'documents'][
                                                                                                    0] else "Нет данных."
        except Exception:
            memory_context = "Память отключена."

        prompt = f"""
        Ты — квантовый алгоритм Smart Money алгосистемы T-Alpha-System.
        Твоя задача — найти оптимальную точку входа, используя анализ зон ликвидности (Поддержки/Сопротивления) и закрытия Гэпов.

        РЫНОЧНАЯ ДАТА:
        {current_state}

        СТРАТЕГИЯ SMART MONEY:
        1. Зоны Ликвидности (Поддержка/Сопротивление): Крупный игрок покупает у зоны Поддержки ({local_low}). Если текущая цена близко к Поддержке, и есть паттерн "Бычье поглощение" — это мощный сигнал BUY.
        2. Закрытие Гэпа (ТОЛЬКО ДЛЯ РЫНКА STOCKS/MOEX): Если рынок фондовый, и есть сильный отрицательный Гэп (например, дивгэп ниже -1.5%), цена с вероятностью 80% стремится закрыть этот гэп вверх. Это дополнительный фактор для BUY от зоны поддержки. Для крипты гэпы игнорируем.
        3. Размещение стопов: Обязательно прячь Stop Loss за зону Поддержки ({local_low} минус волатильность), а Take Profit ставь перед зоной Сопротивления ({local_high}).

        Выдай решение СТРОГО в формате JSON без разметки markdown:
        {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0-100,
            "reason": "Краткое обоснование на русском. Обязательно укажи расстояние до Поддержки/Сопротивления и перспективу закрытия Гэпа (если это Фонда)",
            "take_profit": 0.0,
            "stop_loss": 0.0
        }}
        """

        try:
            with GigaChat(credentials=self.credentials, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [
                        {"role": "system", "content": "Ты - математический алгоритм. Выдавай только JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                })

                result_text = response.choices[0].message.content
                start = result_text.find('{')
                end = result_text.rfind('}') + 1
                decision = json.loads(result_text[start:end])

                if "take_profit" not in decision: decision["take_profit"] = 0.0
                if "stop_loss" not in decision: decision["stop_loss"] = 0.0
                return decision
        except Exception as e:
            return {"action": "HOLD", "confidence": 0, "reason": "Ошибка ИИ", "take_profit": 0.0, "stop_loss": 0.0}


if __name__ == "__main__":
    ai = AIEngine()
    test_inds = {"rsi": 30.5, "local_high": 310.0, "local_low": 280.0, "gap_percent": -5.5, "market_type": "stocks",
                 "pattern": "Бычье поглощение"}
    result = ai.analyze_market_state("SBER", 282.0, 50000, test_inds)
    print(f"AI Response: {result}")