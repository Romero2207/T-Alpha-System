import os
import json
import sys
from dotenv import load_dotenv

# Подключаем корень проекта для доступа к базам
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_vector_db
from gigachat import GigaChat

# Загружаем ключи
load_dotenv()


class AIEngine:
    def __init__(self):
        # Если ключа пока нет, скрипт не упадет, но будет выдавать ошибку при запросе
        self.credentials = os.getenv("GIGACHAT_CREDENTIALS", "")
        self.v_db = get_vector_db()

    def analyze_market_state(self, symbol, current_price, current_volume):
        """Анализирует рынок с учетом прошлой памяти"""

        # 1. Формируем слепок текущего состояния
        current_state = f"Market is trading {symbol} at {current_price} with volume {current_volume}."

        # 2. Ищем похожие рыночные фазы в памяти (ChromaDB)
        # Пока база пуста, она ничего не вернет, но архитектура поиска уже работает
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

            # 3. Формируем жесткий системный промпт
            prompt = f"""
                Ты - аналитическое ядро T-Alpha-System. Твоя задача - фильтровать рыночный шум.
                Текущее состояние: {current_state}
                Память: {memory_context}

                Выдай торговое решение в строгом формате JSON без лишнего текста:
                {{"action": "BUY" | "SELL" | "HOLD", "confidence": 0-100, "reason": "строго до 5 слов на РУССКОМ языке"}}
                """

        # 4. Отправляем запрос в GigaChat
        try:
            # Отключаем проверку сертификатов для стабильной работы локально
            with GigaChat(credentials=self.credentials, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [
                        {"role": "system",
                         "content": "Ты - квантовый торговый алгоритм. Отвечай только валидным JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1  # Низкая температура для логичных, а не творческих ответов
                })

                result_text = response.choices[0].message.content

                # Парсим JSON
                try:
                    # Ищем начало и конец JSON на случай, если ИИ добавил текст
                    start = result_text.find('{')
                    end = result_text.rfind('}') + 1
                    clean_json = result_text[start:end]
                    decision = json.loads(clean_json)
                except json.JSONDecodeError:
                    decision = {"action": "HOLD", "confidence": 0, "reason": "JSON Parsing Error"}

                return decision

        except Exception as e:
            return {"action": "HOLD", "confidence": 0, "reason": f"AI_OFFLINE"}


if __name__ == "__main__":
    print("SYSTEM: Booting AI Engine...")
    ai = AIEngine()

    # Симуляция запроса
    print("SYSTEM: Simulating market state analysis...")
    result = ai.analyze_market_state("BTCUSDT", 65000.50, 120.5)
    print(f"AI Response: {result}")
