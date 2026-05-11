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

    def analyze_market_state(self, symbol, current_price, current_volume, rsi=50.0):
        """Анализирует рынок с учетом памяти и технических индикаторов (RSI)"""

        # 1. Формируем расширенный слепок состояния
        current_state = f"Актив {symbol}. Цена: {current_price}. Объем: {current_volume}. Индикатор RSI: {rsi}."

        # 2. Поиск в векторной памяти
        try:
            similar_patterns = self.v_db.query(
                query_texts=[current_state],
                n_results=1
            )
            memory_context = "Нет похожих исторических данных."
            if similar_patterns['documents'] and similar_patterns['documents'][0]:
                memory_context = "Прошлый опыт: " + " | ".join(similar_patterns['documents'][0])
        except Exception as e:
            memory_context = "Ошибка доступа к памяти."

        # 3. Жесткий системный промпт (добавлена шпаргалка по RSI)
        prompt = f"""
        Ты - аналитическое ядро T-Alpha-System. Твоя задача - фильтровать рыночный шум.

        Текущее состояние: {current_state}
        Память: {memory_context}

        Справка по RSI:
        - RSI > 70: Перекупленность (возможен SELL, если есть подтверждение)
        - RSI < 30: Перепроданность (возможен BUY, если есть подтверждение)
        - RSI от 30 до 70: Нейтральная зона (рекомендуется HOLD)

        Выдай торговое решение в строгом формате JSON без лишнего текста:
        {{"action": "BUY" | "SELL" | "HOLD", "confidence": 0-100, "reason": "строго до 5 слов на РУССКОМ языке"}}
        """

        # 4. Отправка запроса
        try:
            with GigaChat(credentials=self.credentials, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [
                        {"role": "system", "content": "Ты - квантовый алгоритм. Отвечай только валидным JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                })

                result_text = response.choices[0].message.content

                try:
                    start = result_text.find('{')
                    end = result_text.rfind('}') + 1
                    clean_json = result_text[start:end]
                    decision = json.loads(clean_json)
                except json.JSONDecodeError:
                    decision = {"action": "HOLD", "confidence": 0, "reason": "Ошибка парсинга ответа ИИ"}

                return decision

        except Exception as e:
            return {"action": "HOLD", "confidence": 0, "reason": "Сбой связи с нейросетью"}


if __name__ == "__main__":
    print("SYSTEM: Booting AI Engine...")
    ai = AIEngine()
    result = ai.analyze_market_state("BTCUSDT", 65000.50, 120.5, rsi=25.4)
    print(f"AI Response: {result}")