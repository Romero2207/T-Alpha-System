import sys
import os

# Подключаем корень проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_vector_db


def seed_ai_memory():
    print("SYSTEM: Booting AI Memory Matrix...")
    v_db = get_vector_db()

    # Очищаем базу, если мы захотим перезаписать правила
    if v_db.count() > 0:
        # Для локальной разработки проще удалить и создать коллекцию заново,
        # но пока просто добавляем новые знания
        pass

    # Базовые паттерны рынка (Опыт)
    patterns = [
        {
            "id": "pattern_1",
            "state": "Резкое падение цены на высоком объеме.",
            "knowledge": "Это паническая распродажа (Panic Sell). Вероятен отскок (Dead Cat Bounce). Если волатильность зашкаливает, сигнал на BUY опасен. Рекомендуется HOLD до стабилизации объемов."
        },
        {
            "id": "pattern_2",
            "state": "Плавный рост цены при стабильных, средних объемах.",
            "knowledge": "Здоровый восходящий тренд (Bullish Trend). Низкий риск. Это подтвержденный сигнал на BUY. Рынок уверен в активе."
        },
        {
            "id": "pattern_3",
            "state": "Цена стоит на месте, объемы стремительно падают.",
            "knowledge": "Консолидация (Флэт). Крупные игроки ушли с рынка. Сигналы индикаторов в этот момент ложные. Требуется строгий HOLD до появления импульса."
        },
        {
            "id": "pattern_4",
            "state": "Резкий рост цены на аномально высоком объеме после долгого затишья.",
            "knowledge": "Пробой уровня или инсайдерский памп. Если цена ушла слишком высоко, входить в BUY поздно (FOMO). Искать точки фиксации прибыли (SELL) или ждать отката."
        }
    ]

    print(f"SYSTEM: Injecting {len(patterns)} fundamental market patterns into ChromaDB...")

    for p in patterns:
        v_db.upsert(
            ids=[p["id"]],
            documents=[p["knowledge"]],
            metadatas=[{"market_state": p["state"]}]
        )

    print(f"SYSTEM: Memory update complete. Total patterns in memory: {v_db.count()}")


if __name__ == "__main__":
    seed_ai_memory()