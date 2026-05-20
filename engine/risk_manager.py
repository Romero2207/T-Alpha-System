import json
import os


class RiskManager:
    def __init__(self):
        self.crypto_mode = "low"
        self.moex_mode = "low"
        self.settings_file = "settings.json"

    def load_settings(self):
        """Подтягиваем настройки, которые ты сохраняешь на сайте"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    self.crypto_mode = data.get("crypto", "low")
                    self.moex_mode = data.get("moex", "low")
        except:
            pass

    def approve_signal(self, symbol, action, price, rsi):
        # 1. Перед каждой проверкой обновляем настройки из файла
        self.load_settings()

        # 2. Определяем, какой рынок торгуется
        mode = self.crypto_mode if "USDT" in symbol else self.moex_mode

        # 3. ЛОГИКА РИСКА
        if action == "BUY":
            # В Low Risk бот боится покупать, если RSI выше 65. В Medium Risk (Агрессивно) он покупает вплоть до RSI 75.
            max_rsi = 75 if mode == "medium" else 65
            if rsi > max_rsi:
                return False, f"БЛОК: RSI={rsi} слишком перегрет для покупки (Режим: {mode.upper()})"

        elif action == "SELL":
            # Для продажи (шорта) логика зеркальная
            min_rsi = 25 if mode == "medium" else 35
            if rsi < min_rsi:
                return False, f"БЛОК: RSI={rsi} слишком перепродан для шорта (Режим: {mode.upper()})"

        # Если фильтры пройдены:
        return True, "Риски в норме. Одобрено."