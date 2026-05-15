import os
import requests
from dotenv import load_dotenv

load_dotenv()


class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TG_BOT_TOKEN")
        self.chat_id = os.getenv("TG_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        # Обойма прокси-серверов (Бот будет перебирать их по очереди)
        self.proxies_list = [
            {'http': 'http://188.166.83.13:3128', 'https': 'http://188.166.83.13:3128'},
            {'http': 'http://8.210.83.33:80', 'https': 'http://8.210.83.33:80'},
            {'http': 'http://103.152.112.162:80', 'https': 'http://103.152.112.162:80'},
            {'http': 'http://152.67.115.115:8080', 'https': 'http://152.67.115.115:8080'},
            {'http': 'http://198.199.86.11:8080', 'https': 'http://198.199.86.11:8080'},
            {'http': 'http://167.71.204.148:8080', 'https': 'http://167.71.204.148:8080'}
        ]

    def send_signal(self, symbol, action, price, reason, change, tp, sl):
        if not self.token or not self.chat_id:
            return

        if "BUY" in action:
            icon = "🟢 СИГНАЛ НА ПОКУПКУ (LONG)"
        elif "SELL" in action:
            icon = "🔴 СИГНАЛ НА ПРОДАЖУ (SHORT)"
        else:
            return  # Не спамим при HOLD

        # Автоматически определяем рынок
        market_tag = "🪙 Криптовалюта (Bybit)" if symbol.endswith("USDT") else "🏛️ Фондовый рынок (MOEX)"
        fiat_sign = "$" if symbol.endswith("USDT") else "₽"

        msg = (
            f"{icon}\n\n"
            f"🌐 Рынок: <b>{market_tag}</b>\n"
            f"💎 Актив: <b>{symbol}</b>\n"
            f"💰 Текущая цена: {fiat_sign}{price:,.4f}\n"
            f"📊 Динамика 24ч: {change:+.2f}%\n"
            f"🧠 Вердикт ИИ: <i>{reason}</i>\n\n"
            f"🎯 Take Profit: {fiat_sign}{tp:,.4f}\n"
            f"🛡 Stop Loss: {fiat_sign}{sl:,.4f}"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }

        try:
            # 1. Сначала пробуем прямой запрос (вдруг провайдер отпустил блокировку)
            requests.post(self.api_url, data=payload, timeout=5)
            return
        except requests.exceptions.ConnectionError:
            pass  # Прямой запрос не прошел, идем к прокси

        # 2. Быстро перебираем список резервных прокси
        print("Прямое соединение с Telegram заблокировано. Подбираем рабочий прокси...")
        for px in self.proxies_list:
            try:
                requests.post(self.api_url, data=payload, proxies=px, timeout=4)
                print(f"✅ Уведомление успешно отправлено (через {px['http']})")
                return  # Успех - выходим из функции
            except Exception:
                continue  # Этот прокси мертв, пробуем следующий

        print("⚠️ Не удалось отправить в Telegram: все бесплатные резервные прокси из списка сейчас недоступны.")


if __name__ == "__main__":
    bot = TelegramNotifier()
    bot.send_signal("BTCUSDT", "BUY", 82000.50, "Бычье поглощение", 2.5, 85000.0, 80000.0)
    print("Тест завершен.")