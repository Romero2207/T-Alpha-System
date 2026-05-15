import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection


class PortfolioManager:
    def __init__(self):
        self._init_balances()

    def _init_balances(self):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT amount FROM portfolio WHERE symbol='USDT'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO portfolio (symbol, amount) VALUES ('USDT', 10000.0)")

        cursor.execute("SELECT amount FROM portfolio WHERE symbol='RUB'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO portfolio (symbol, amount) VALUES ('RUB', 100000.0)")

        conn.commit()
        conn.close()

    def monitor_positions(self, symbol, current_price, notifier=None):
        """Проверяет TP, SL и Трейлинг-стоп для активных позиций"""
        conn = get_connection()
        cursor = conn.cursor()

        # Проверяем, есть ли нужные колонки (защита от старой БД)
        try:
            cursor.execute(
                "SELECT amount, average_entry_price, take_profit, stop_loss, high_water_mark FROM portfolio WHERE symbol=?",
                (symbol,))
            row = cursor.fetchone()
        except Exception as e:
            conn.close()
            return False

        if not row or row['amount'] <= 0:
            conn.close()
            return False

        amt = row['amount']
        entry = row['average_entry_price']
        tp = row['take_profit']
        sl = row['stop_loss']
        hwm = row['high_water_mark']

        # 1. Обновляем Пик цены (High Water Mark)
        if current_price > hwm:
            cursor.execute("UPDATE portfolio SET high_water_mark=? WHERE symbol=?", (current_price, symbol))
            conn.commit()
            hwm = current_price

        # 2. Логика Трейлинг-стопа (Динамический выход)
        trailing_drop_pct = 1.5
        trailing_stop_price = hwm * (1 - (trailing_drop_pct / 100))

        sell_reason = None
        if tp > 0 and current_price >= tp:
            sell_reason = f"🎯 Сработал Take Profit (+{((current_price - entry) / entry) * 100:.2f}%)"
        elif sl > 0 and current_price <= sl:
            sell_reason = f"🛡 Сработал Stop Loss ({((current_price - entry) / entry) * 100:.2f}%)"
        elif current_price <= trailing_stop_price and hwm > entry * 1.01:
            sell_reason = f"📉 Трейлинг-стоп: Откат {trailing_drop_pct}% от пика (+{((current_price - entry) / entry) * 100:.2f}%)"

        conn.close()

        # Выполняем авто-продажу
        if sell_reason:
            self.execute_paper_trade(symbol, "SELL", current_price, reason=sell_reason)
            if notifier:
                notifier.send_signal(symbol, "SELL (AUTO-EXIT)", current_price, sell_reason, 0, 0, 0)
            return True
        return False

    def execute_paper_trade(self, symbol, action, price, tp=0.0, sl=0.0, reason="Ручной ордер"):
        conn = get_connection()
        cursor = conn.cursor()

        fiat_symbol = "RUB" if symbol in ["SBER", "GAZP", "LKOH", "YNDX", "TCSG", "TATN", "AQUA"] else "USDT"
        trade_size_fiat = 10000.0 if fiat_symbol == "RUB" else 1000.0

        cursor.execute("SELECT amount FROM portfolio WHERE symbol=?", (fiat_symbol,))
        fiat_balance = cursor.fetchone()[0]

        cursor.execute("SELECT amount, average_entry_price FROM portfolio WHERE symbol=?", (symbol,))
        asset_row = cursor.fetchone()
        asset_balance = asset_row[0] if asset_row else 0.0
        avg_entry = asset_row[1] if asset_row else 0.0

        trade_executed = False
        amount_traded = 0.0

        if action == "BUY" and fiat_balance >= trade_size_fiat:
            amount_traded = trade_size_fiat / price
            new_fiat = fiat_balance - trade_size_fiat
            new_asset = asset_balance + amount_traded
            new_avg_entry = ((asset_balance * avg_entry) + (
                        amount_traded * price)) / new_asset if new_asset > 0 else price

            cursor.execute("UPDATE portfolio SET amount=? WHERE symbol=?", (new_fiat, fiat_symbol))

            # ВАЖНО: Записываем tp, sl и hwm
            if asset_row:
                cursor.execute(
                    "UPDATE portfolio SET amount=?, average_entry_price=?, take_profit=?, stop_loss=?, high_water_mark=? WHERE symbol=?",
                    (new_asset, new_avg_entry, tp, sl, price, symbol))
            else:
                cursor.execute(
                    "INSERT INTO portfolio (symbol, amount, average_entry_price, take_profit, stop_loss, high_water_mark) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, new_asset, new_avg_entry, tp, sl, price))
            trade_executed = True

        elif ("SELL" in action) and asset_balance > 0:
            amount_traded = asset_balance
            gained_fiat = amount_traded * price
            new_fiat = fiat_balance + gained_fiat

            cursor.execute("UPDATE portfolio SET amount=? WHERE symbol=?", (new_fiat, fiat_symbol))
            # При продаже обнуляем стопы
            cursor.execute(
                "UPDATE portfolio SET amount=0, average_entry_price=0, take_profit=0, stop_loss=0, high_water_mark=0 WHERE symbol=?",
                (symbol,))
            trade_executed = True

        if trade_executed:
            cursor.execute(
                "INSERT INTO trade_history (symbol, action, price, amount, total_value, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (symbol, action, price, amount_traded, amount_traded * price, reason)
            )

        conn.commit()
        conn.close()
        return trade_executed