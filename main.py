import asyncio
import sys
import os
import requests
import uvicorn
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

from core.event_bus import SystemEventBus
from engine.data_collector import AsyncDataCollector
from engine.brain_node import BrainNode
import ui.web_server as web_ui
from core.memory import get_connection
from core.notifier import TelegramNotifier

load_dotenv()

bybit_scanner = HTTP(testnet=False)

# ВОТ ЭТА СТРОЧКА РЕШИТ ПРОБЛЕМУ:
tg_bot = TelegramNotifier()


async def stop_loss_scanner(bus):
    """Фоновый сканер: автоматически закрывает сделки по TP и SL"""
    print("🛡️ [Risk Scanner] Автоматический контроль позиций запущен...")
    while bus.is_running:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            # Ищем все купленные активы, у которых выставлены стопы
            cursor.execute(
                "SELECT symbol, amount, average_entry_price, sl, tp FROM portfolio WHERE amount > 0 AND sl > 0 AND tp > 0")
            positions = cursor.fetchall()
            conn.close()

            for pos in positions:
                symbol, amount, entry, sl, tp = pos
                current_price = entry

                # 1. Узнаем текущую живую цену
                try:
                    if "USDT" in symbol:
                        res = bybit_scanner.get_tickers(category="linear", symbol=symbol)
                        if res.get('retCode') == 0:
                            current_price = float(res['result']['list'][0]['lastPrice'])
                    else:
                        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}.json?iss.only=marketdata"
                        res = requests.get(url, timeout=2).json()
                        cols = res['marketdata']['columns']
                        row = res['marketdata']['data'][0]
                        current_price = float(row[cols.index('LAST')] or entry)
                except:
                    continue

                # 2. Проверяем пересечение линий
                signal = None
                if current_price <= sl:
                    print(f"🛑 [Risk Scanner] ВЫБИЛО СТОП-ЛОСС по {symbol}! Цена: {current_price}")
                    signal = {"symbol": symbol, "action": "SELL (Stop-Loss)", "price": current_price, "confidence": 100,
                              "reason": f"Цена упала до уровня SL ({sl})", "sl": 0, "tp": 0}
                elif current_price >= tp:
                    print(f"🎯 [Risk Scanner] ТЕЙК-ПРОФИТ ВЗЯТ по {symbol}! Цена: {current_price}")
                    signal = {"symbol": symbol, "action": "SELL (Take-Profit)", "price": current_price,
                              "confidence": 100, "reason": f"Цена достигла профита TP ({tp})", "sl": 0, "tp": 0}

                # 3. Отправляем сигнал на продажу
                if signal:
                    await bus.publish("TRADE_SIGNAL", signal)

        except Exception as e:
            pass

        # Сканируем каждые 3 секунды
        await asyncio.sleep(3)


async def execute_trade(payload):
    """Модуль исполнения: отправляет реальные ордера на Bybit Testnet из файла .env"""
    symbol = payload['symbol']
    action = payload['action']
    price = payload['price']
    sl = payload.get('sl', 0)
    tp = payload.get('tp', 0)

    # Мы торгуем фьючерсы крипты к USDT
    if "USDT" not in symbol:
        return

    try:
        # Читаем ключи напрямую из системного окружения (.env)
        api_key = os.getenv("BYBIT_TESTNET_API_KEY")
        api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

        # Если ключи в .env не найдены, бот безопасно перейдет в режим симуляции в локальную БД
        if not api_key or not api_secret:
            print("⚠️ [Execution] Ордер симулирован: не найдены API-ключи в файле .env")
            save_order_to_local_db(symbol, action, price, sl, tp)
            return

        from pybit.unified_trading import HTTP
        session = HTTP(
            testnet=True,  # Включаем режим Песочницы (Bybit Testnet)
            api_key=api_key,
            api_secret=api_secret
        )

        # Рассчитываем объем сделки: заходим на фиксированные виртуальные 100 USDT
        qty = round(100 / price, 3)
        side = "Buy" if "BUY" in action else "Sell"

        print(f"📡 [Execution] Отправка ордера на Bybit Testnet: {side} {symbol} объем {qty}...")

        # 1. Отправляем приказ на биржу Bybit
        order = session.place_order(
            category="linear",  # Категория линейных бессрочных фьючерсов
            symbol=symbol,
            side=side,
            orderType="Market",  # Покупаем/Продаем мгновенно по текущей рыночной цене
            qty=str(qty),
            timeInForce="GTC"
        )

        # 2. ВОТ СЮДА ВСТАВЛЯЕМ НАШ БЛОК ПРОВЕРКИ И ТЕЛЕГРАМА:
        if order.get('retCode') == 0:
            order_id = order['result']['orderId']
            print(f"✅ [Bybit API] Ордер успешно исполнен биржей! ID: {order_id}")
            save_order_to_local_db(symbol, action, price, sl, tp, actual_qty=qty)

            # ОТПРАВКА В ТЕЛЕГРАМ (работает в фоне, не тормозит систему)
            reason = payload.get('reason', 'Сигнал алгоритма')
            asyncio.create_task(tg_bot.send_signal(symbol, action, price, reason, tp, sl))

        else:
            print(f"❌ [Bybit API] Биржа отклонила ордер: {order.get('retMsg')}")

    except Exception as e:
        print(f"❌ [Execution] Критическая ошибка API-модуля: {e}")


def save_order_to_local_db(symbol, action, price, sl, tp, actual_qty=0):
    """Вспомогательная функция: записывает сделки в локальную БД для отображения на сайте"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Безопасно проверяем колонки
        try:
            cursor.execute("ALTER TABLE portfolio ADD COLUMN sl REAL DEFAULT 0")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE portfolio ADD COLUMN tp REAL DEFAULT 0")
        except:
            pass

        cursor.execute("SELECT amount FROM portfolio WHERE symbol = ?", (symbol,))
        row = cursor.fetchone()
        current_amount = row[0] if row else 0

        trade_size = 100
        amount = actual_qty if actual_qty > 0 else (trade_size / price)
        if "SELL" in action:
            amount = current_amount

        total_value = amount * price

        if amount > 0:
            cursor.execute("""
                INSERT INTO trade_history (timestamp, symbol, action, price, amount, total_value) 
                VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?)
            """, (symbol, action, price, amount, total_value))

            if "BUY" in action:
                new_amount = current_amount + amount
                cursor.execute("SELECT id FROM portfolio WHERE symbol = ?", (symbol,))
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE portfolio SET amount = ?, average_entry_price = ?, sl = ?, tp = ? WHERE symbol = ?",
                        (new_amount, price, sl, tp, symbol))
                else:
                    cursor.execute(
                        "INSERT INTO portfolio (symbol, amount, average_entry_price, sl, tp) VALUES (?, ?, ?, ?, ?)",
                        (symbol, new_amount, price, sl, tp))
            elif "SELL" in action:
                cursor.execute(
                    "UPDATE portfolio SET amount = 0, average_entry_price = 0, sl = 0, tp = 0 WHERE symbol = ?",
                    (symbol,))

            conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка локального сохранения: {e}")

async def run_fastapi():
    config = uvicorn.Config(web_ui.app, host="127.0.0.1", port=8000, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    print("Инициализация T-Alpha Core...")
    # --- ГЛУШИТЕЛЬ ОШИБКИ WinError 10054 ---
    loop = asyncio.get_running_loop()

    def handle_exception(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError) and exc.winerror == 10054:
            return  # Просто игнорируем этот системный спам Windows
        loop.default_exception_handler(context)

    loop.set_exception_handler(handle_exception)
    bus = SystemEventBus()
    web_ui.system_bus = bus

    collector = AsyncDataCollector(bus)
    brain = BrainNode(bus)

    bus.subscribe("MARKET_TICK", brain.handle_tick)
    bus.subscribe("TRADE_SIGNAL", execute_trade)

    bus_task = asyncio.create_task(bus.run())
    collector_task = asyncio.create_task(collector.run())
    web_task = asyncio.create_task(run_fastapi())
    scanner_task = asyncio.create_task(stop_loss_scanner(bus))  # Запускаем фоновый контроль рисков

    print("✅ Сервер запущен! Открой в браузере: http://127.0.0.1:8000")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановка системы...")
    finally:
        bus.is_running = False
        collector.is_running = False
        bus_task.cancel()
        collector_task.cancel()
        web_task.cancel()
        scanner_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())