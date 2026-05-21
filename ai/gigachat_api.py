import os
import json
from gigachat import GigaChat


class GigaChatTrader:
    def __init__(self):
        self.credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not self.credentials:
            print("⚠️ [GigaChat] Ключ не найден в .env! ИИ отключен.")

    def analyze_market_state(self, symbol, current_price, volume, inds, market_type="crypto"):
        if not self.credentials:
            return {"action": "HOLD", "confidence": 0, "reason": "Ключ не настроен", "take_profits": [], "sl": 0,
                    "leverage": 1, "trailing": False}

        # --- ЧИТАЕМ ОПЫТ ИЗ БАЗЫ ---
        bot_experience = "У тебя пока нет опыта торговли этим активом. Будь осторожен."
        try:
            if os.path.exists("ai_experience.json"):
                with open("ai_experience.json", "r") as f:
                    exp_db = json.load(f)
                    if symbol in exp_db:
                        coin_exp = exp_db[symbol]
                        bot_experience = f"ТВОЙ ПРОШЛЫЙ ОПЫТ НА {symbol}: Winrate {coin_exp['winrate']}%, Профит ${coin_exp['profit']}. Сделок: {coin_exp['trades']}. "
                        if coin_exp['winrate'] > 60:
                            bot_experience += "Монета отлично читается алгоритмом, можно торговать агрессивно."
                        else:
                            bot_experience += "Монета коварная, ставь короткие стопы и тейки."
        except:
            pass
        # ----------------------------

        rsi = inds.get("rsi", 50)
        pattern = inds.get("pattern", "None")
        sma = inds.get("sma", current_price)
        poc = inds.get("poc", current_price)

        trend = "UPTREND (Восходящий)" if current_price > sma else "DOWNTREND (Нисходящий)"

        # 🧠 ДВА ПОЛУШАРИЯ ИИ
        if market_type == "crypto":
            market_rules = """
РЫНОК: КРИПТОВАЛЮТА (Консервативный режим 1х)
- Плечо (leverage): Строго 1 (БЕЗ ПЛЕЧА).
- Вход: Ищи ювелирные точки. RSI < 30 (Лонг на самом дне) или RSI > 70 (Шорт на пике).
- Выход (Take Profits): Не жадничай. BTC/ETH не ходят по 10% за час. Сформируй сетку из мелких тейков: TP1 (+0.8%), TP2 (+1.5%), TP3 (+2.5%).
- Защита (Stop Loss): Короткий стоп-лосс на -1.0% от цены входа.
- Trailing Stop: включен (true).
"""
        else:
            market_rules = """
РЫНОК: ФОНДОВЫЙ РЫНОК / АКЦИИ РФ (Спокойный, с гэпами)
- Плечо (leverage): Строго 1 (Без плеча).
- Вход: RSI < 45, покупка на сильных просадках (Только BUY, без шортов).
- Выход (Take Profits): Сформируй массив из 2-х цен. TP1 (+0.8%), TP2 (+1.5%).
- Защита (Stop Loss): БЕЗ СТОП-ЛОССА. Ставь значение 0. Акции мы готовы пересиживать.
- Trailing Stop: выключен (false).
"""

        system_prompt = f"""Ты — T-Alpha, продвинутый ИИ-алготрейдер. 
Твоя задача: анализировать индикаторы и выдавать строго JSON с торговым решением. Не пиши текст вне JSON.

{market_rules}

ФОРМАТ ОТВЕТА (Строго JSON):
{{
    "action": "BUY", // или SELL (только для крипты), или HOLD
    "confidence": 85,
    "reason": "RSI в зоне перепроданности. Ожидаю отскок.",
    "leverage": 2, 
    "take_profits": [<цена_tp1>, <цена_tp2>, <цена_tp3>], 
    "stop_loss": <цена_sl_или_0>,
    "trailing_stop": true
}}
ВНИМАНИЕ: take_profits - это массив чисел (абсолютные цены, а не проценты!).
"""
        user_prompt = f"""ДАННЫЕ: Монета/Акция: {symbol} | Цена: {current_price} | Тренд: {trend} | RSI: {rsi} | Паттерн: {pattern} | База POC: {poc}
ТВОЕ РЕШЕНИЕ (только JSON):"""

        try:
            with GigaChat(credentials=self.credentials, verify_ssl_certs=False) as giga:
                response = giga.chat({
                    "messages": [{"role": "system", "content": system_prompt},
                                 {"role": "user", "content": user_prompt}],
                    "temperature": 0.1, "max_tokens": 150
                })

                result_text = response.choices[0].message.content
                start, end = result_text.find('{'), result_text.rfind('}') + 1
                decision = json.loads(result_text[start:end]) if start != -1 and end != -1 else {"action": "HOLD"}

                print(
                    f"💭 [GigaChat] {symbol} ({market_type.upper()}): {decision.get('action')} | Плечо: x{decision.get('leverage', 1)} | Уверенность: {decision.get('confidence', 0)}%")

                decision["tp"] = decision.get("take_profits", [])
                decision["sl"] = decision.get("stop_loss", 0)
                if decision.get("action") == "HOLD": decision["tp"] = []; decision["sl"] = 0
                return decision

        except Exception as e:
            return {"action": "HOLD", "confidence": 0, "reason": str(e), "tp": [], "sl": 0}