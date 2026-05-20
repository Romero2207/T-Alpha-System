import json
import os


class RiskManager:
    def __init__(self):
        self.crypto_mode = "low"
        self.moex_mode = "low"
        self.settings_file = "settings.json"

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    self.crypto_mode = data.get("crypto", "low")
                    self.moex_mode = data.get("moex", "low")
        except:
            pass

    def approve_signal(self, symbol, action, price, inds):
        self.load_settings()
        mode = self.crypto_mode if "USDT" in symbol else self.moex_mode

        rsi = inds.get('rsi', 50)
        # Если ATR вдруг не рассчитался, берем 1% от цены как базовую волатильность
        atr = inds.get('atr') if inds.get('atr') and inds.get('atr') > 0 else (price * 0.01)

        # Множители ATR (В агрессивном режиме даем цене больше пространства для маневра)
        sl_mult = 2.0 if mode == "medium" else 1.5
        rr_ratio = 2.5 if mode == "medium" else 2.0  # Риск/Прибыль 1:2.5 или 1:2.0

        sl_price, tp_price = 0.0, 0.0

        if action == "BUY":
            max_rsi = 75 if mode == "medium" else 65
            if rsi > max_rsi:
                return False, f"БЛОК: RSI={rsi} перегрет (Режим: {mode.upper()})", 0, 0

            # Считаем уровни для лонга
            sl_price = price - (atr * sl_mult)
            tp_price = price + (atr * sl_mult * rr_ratio)

        elif action == "SELL":
            min_rsi = 25 if mode == "medium" else 35
            if rsi < min_rsi:
                return False, f"БЛОК: RSI={rsi} перепродан (Режим: {mode.upper()})", 0, 0

            # Считаем уровни для шорта
            sl_price = price + (atr * sl_mult)
            tp_price = price - (atr * sl_mult * rr_ratio)

        return True, f"Одобрено. Risk/Reward 1:{rr_ratio}", round(sl_price, 4), round(tp_price, 4)