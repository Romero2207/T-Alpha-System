import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TG_BOT_TOKEN")
        self.chat_id = os.getenv("TG_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        # Бесплатные HTTP прокси (если основной канал заблокирован)
        self.proxies_list = [
            'http://188.166.83.13:3128',
            'http://152.67.115.115:8080',
            'http://198.199.86.11:8080',
            'http://167.71.204.148:8080'
        ]

    async def send_signal(self, symbol, action, price, reason, tp, sl):
        if not self.token or not self.chat_id:
            return

        if "BUY" in action:
            icon = "🟢 СИГНАЛ НА ПОКУПКУ"
        elif "SELL" in action:
            icon = "🔴 СИГНАЛ НА ПРОДАЖУ"
        else:
            return  # Не спамим при HOLD

        market_tag = "🪙 Криптовалюта (Bybit)" if "USDT" in symbol else "🏛️ Фондовый рынок (MOEX)"
        fiat_sign = "$" if "USDT" in symbol else "₽"

        msg = (
            f"{icon}\n\n"
            f"🌐 Рынок: <b>{market_tag}</b>\n"
            f"💎 Актив: <b>{symbol}</b>\n"
            f"💰 Цена: {fiat_sign}{price:,.4f}\n\n"
            f"🎯 Take Profit: {fiat_sign}{tp:,.4f}\n"
            f"🛑 Stop Loss: {fiat_sign}{sl:,.4f}\n\n"
            f"🧠 Вердикт ИИ: <i>{reason}</i>"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }

        # Асинхронная отправка, чтобы не тормозить торгового бота
        async with aiohttp.ClientSession() as session:
            try:
                # 1. Пробуем напрямую
                async with session.post(self.api_url, data=payload, timeout=4) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                pass  # Прямой доступ заблокирован, идем к прокси

            # 2. Быстрый перебор прокси
            print("📡 [Telegram] Прямой доступ заблокирован, пробуем прокси...")
            for px in self.proxies_list:
                try:
                    async with session.post(self.api_url, data=payload, proxy=px, timeout=3) as resp:
                        if resp.status == 200:
                            print(f"✅ [Telegram] Сообщение отправлено через прокси!")
                            return
                except Exception:
                    continue