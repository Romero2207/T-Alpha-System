import os
import requests
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TG_BOT_TOKEN")
        self.chat_id = os.getenv("TG_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, symbol, action, price, reason, change, tp, sl):
        if not self.token or not self.chat_id:
            print("Telegram ключи не найдены в .env")
            return

        if "BUY" in action:
            icon = "🟢 СИГНАЛ НА ПОКУПКУ (LONG)"
        elif "SELL" in action:
            icon = "🔴 СИГНАЛ НА ПРОДАЖУ (SHORT)"
        else:
            return  # Не спамим при HOLD

        msg = (
            f"{icon}\n\n"
            f"💎 Актив: <b>{symbol}</b>\n"
            f"💰 Текущая цена: ${price:,.4f}\n"
            f"📊 Динамика 24ч: {change:+.2f}%\n"
            f"🧠 Вердикт ИИ: <i>{reason}</i>\n\n"
            f"🎯 Take Profit: ${tp:,.4f}\n"
            f"🛡 Stop Loss: ${sl:,.4f}"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }

        try:
            # Сначала пробуем прямой запрос (у многих работает без проблем)
            requests.post(self.api_url, data=payload, timeout=5)
        except requests.exceptions.ConnectionError:
            # Если провайдер блокирует api.telegram.org, идем через бесплатный прокси
            print("Прямое соединение с Telegram заблокировано. Пробуем через прокси...")
            proxies = {
                'http': 'http://188.166.195.122:3128',
                'https': 'http://188.166.195.122:3128'
            }
            try:
                requests.post(self.api_url, data=payload, proxies=proxies, timeout=10)
            except Exception as e:
                print(f"Ошибка отправки в Telegram даже через прокси: {e}")
        except Exception as e:
            print(f"Неизвестная ошибка Telegram: {e}")

if __name__ == "__main__":
    # Для теста просто запусти этот файл!
    bot = TelegramNotifier()
    print("Отправка тестового сообщения...")
    bot.send_signal("BTCUSDT", "BUY", 82000.50, "Бычье поглощение + RSI дно", 2.5, 85000.0, 80000.0)
    print("Скрипт завершил работу. Проверь телефон!")