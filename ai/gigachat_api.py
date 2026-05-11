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
        # indicators - это теперь словарь: rsi, macd_hist, bb_high, bb_low, atr

        current_state = f"Актив {symbol}. Цена: {current_price}. RSI: {indicators['rsi']}. MACD-Гистограмма: {indicators['macd_hist']}. Верх Боллинджера: {indicators['bb_high']}. Низ Боллинджера: {indicators['bb_low']}. ATR: {indicators['atr']}."

        try:
            similar_patterns = self.v_db.query(query_texts=[current_state], n_results=1)
            memory_context = "Прошлый опыт: " + " | ".join(similar_patterns['documents'][0]) if similar_patterns[
                                                                                                    'documents'] and \
                                                                                                similar_patterns[
                                                                                                    'documents'][
                                                                                                    0] else "Нет данных."
        except Exception:
            memory_context = "Ошибка памяти."

        prompt = f"""
        Ты - профессиональный алготрейдер T-Alpha-System.
        Текущее состояние: {current_state}
        Память: {memory_context}

        ШПАРГАЛКА ПО ИНДИКАТОРАМ (Конфлюэнция):
        1. RSI: >70 (Перекуплен), <30 (Перепродан).
        2. MACD-Гистограмма: > 0 (Тренд восходящий/бычий), < 0 (Тренд нисходящий/медвежий).
        3. Bollinger Bands: Цена близка к bb_low - поддержка. Близка к bb_high - сопротивление.
        4. ATR: Среднее движение цены. Используй его для установки стопов! (Например, Stop Loss = Цена - 1.5 * ATR).

        ПРАВИЛА СДЕЛКИ:
        - Ищи СОВПАДЕНИЯ. Если RSI < 30 (надо брать), но MACD < 0 (тренд падает), то это риск! Лучше HOLD.
        - Выдай BUY, если актив перепродан и тренд меняется вверх.
        - Выдай SELL, если актив перегрет и тренд меняется вниз.

        Выдай решение в строгом JSON:
        {{
            "action": "BUY" | "SELL" | "HOLD", 
            "confidence": 0-100, 
            "reason": "кратко на русском, например 'RSI дно, MACD разворот'",
            "take_profit": 0.0,
            "stop_loss": 0.0
        }}
        """

        try:
            with GigaChat(credentials=self.credentials, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [
                        {"role": "system", "content": "Ты - математический алгоритм. Отвечай только валидным JSON."},
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

        except Exception:
            return {"action": "HOLD", "confidence": 0, "reason": "Сбой связи", "take_profit": 0, "stop_loss": 0}
if __name__ == "__main__":
    ai = AIEngine()
    result = ai.analyze_market_state("BTCUSDT", 65000.50, 120.5, rsi=25.4)
    print(f"AI Response: {result}")