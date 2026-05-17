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
        """
        Продвинутый ИИ-анализ рыночной структуры.
        Сочетает семантический технический анализ, мульти-таймфреймы и новостной сентимент.
        """
        # Безопасное извлечение базовых и расширенных параметров из словаря индикаторов
        rsi = indicators.get('rsi', 50.0)
        macd = indicators.get('macd_hist', 0.0)
        atr = indicators.get('atr', 0.0)
        pattern = indicators.get('pattern', 'Нет явного паттерна')

        # Интеграция новых фишек (новости и макро-тренды)
        news_sentiment = indicators.get('news_sentiment', 0.0)
        news_feed = indicators.get('news_feed', 'Аномальных новостных событий не зафиксировано.')
        sma200 = indicators.get('sma200', 0.0)

        # Формируем комплексный семантический вектор рынка для промпта
        macro_trend_desc = "НЕОПРЕДЕЛЕННЫЙ"
        if sma200 > 0:
            macro_trend_desc = "ГЛОБАЛЬНЫЙ БЫЧИЙ (Цена выше SMA 200)" if current_price > sma200 else "ГЛОБАЛЬНЫЙ МЕДВЕЖИЙ (Цена ниже SMA 200)"

        current_state = (
            f"Актив: {symbol}. Текущая цена: {current_price}. Суточный объем торгов: {current_volume}.\n"
            f"--- ТЕХНИЧЕСКИЙ ВЕКТОР (Младший ТФ): ---\n"
            f"• Импульсный RSI (14): {rsi}\n"
            f"• Направление MACD Hist: {macd}\n"
            f"• Волатильность ATR: {atr}\n"
            f"• Свечной паттерн поглощения: {pattern}\n"
            f"--- СТРАТЕГИЧЕСКИЙ КОНТЕКСТ (Старший ТФ): ---\n"
            f"• Глобальный макро-тренд: {macro_trend_desc} (Дневная SMA 200 = {sma200})\n"
            f"--- ИНФОРМАЦИОННЫЙ СЕНТИМЕНТ: ---\n"
            f"• Оценка новостного фона: {news_sentiment:.2f} (Шкала от -1.0 до +1.0)\n"
            f"• Свежие заголовки: '{news_feed}'"
        )

        # Обращение к векторной памяти паттернов
        try:
            similar_patterns = self.v_db.query(query_texts=[current_state], n_results=1)
            memory_context = "Прошлый исторический опыт системы: " + " | ".join(similar_patterns['documents'][0]) if \
            similar_patterns['documents'] and similar_patterns['documents'][
                0] else "Нет релевантных совпадений в памяти."
        except Exception:
            memory_context = "Модуль векторной памяти временно недоступен."

        # Профессиональный промпт для глубокого анализа (Order Flow + Smart Money)
        prompt = f"""
        Ты — ведущий квантовый аналитик и ИИ-мозг институциональной алгосистемы T-Alpha-System.
        Твоя задача — провести комплексную кросс-валидацию рыночных данных, выявить ловушки маркетмейкеров и выдать строгое торговое решение.

        АНАЛИЗИРУЕМЫЙ СЛЕПОК РЫНКА:
        {current_state}

        КОНТЕКСТ ПАМЯТИ:
        {memory_context}

        ИНСТРУКЦИЯ ПО СИНТЕЗУ ДАННЫХ:
        1. Кросс-Таймфрейм: Никогда не открывай BUY ордер, если глобальный макро-тренд МЕДВЕЖИЙ, за исключением случаев экстремальной перепроданности (RSI < 20).
        2. Объемы и ТА: Если Свечной паттерн показывает "Бычье поглощение", но MACD падает или объемы торгов снижаются — это ложный пробой (бычья ловушка). Игнорируй его.
        3. Новостной сентимент: Сентимент ниже -0.30 аннулирует любые технические сигналы на покупку. Не пытайся ловить "падающие ножи".
        4. Уровни выхода: На основе волатильности ATR рассчитай Take Profit и Stop Loss. Помни, соотношение Risk/Reward должно быть не менее 1:2.

        Ты должен ответить СТРОГО в формате валидного JSON-объекта (без лишнего текста, без форматирования ```json):
        {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0-100,
            "reason": "Глубокое аналитическое обоснование на русском языке. Опиши взаимосвязь паттерна, глобального тренда и новостей (например: 'Паттерн подтвержден всплеском объема на фоне позитивного сентимента, глобальный тренд лонговый')",
            "take_profit": 0.0,
            "stop_loss": 0.0
        }}
        """

        try:
            with GigaChat(credentials=self.credentials, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [
                        {"role": "system",
                         "content": "Ты - беспристрастный математический алгоритм. Ты генерируешь только чистый, валидный JSON-код без markdown-разметки."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1  # Минимальная температура для исключения галлюцинаций
                })

                result_text = response.choices[0].message.content
                start = result_text.find('{')
                end = result_text.rfind('}') + 1
                decision = json.loads(result_text[start:end])

                # Защитные проверки полей
                if "take_profit" not in decision: decision["take_profit"] = 0.0
                if "stop_loss" not in decision: decision["stop_loss"] = 0.0
                return decision

        except Exception as e:
            return {
                "action": "HOLD",
                "confidence": 0,
                "reason": f"Внутренний тайм-аут ИИ-ядра или сбой парсинга JSON: {str(e)}",
                "take_profit": 0.0,
                "stop_loss": 0.0
            }


if __name__ == "__main__":
    ai = AIEngine()
    test_indicators = {
        "rsi": 28.5, "macd_hist": 0.004, "atr": 150.0, "pattern": "Бычье поглощение",
        "news_sentiment": 0.45, "news_feed": "Крупный фонд задекларировал покупку актива.", "sma200": 62000.0
    }
    result = ai.analyze_market_state("BTCUSDT", 64500.0, 45000000, test_indicators)
    print(f"AI Advanced Response: {result}")