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

    def execute_paper_trade(self, symbol, action, price):
        conn = get_connection()
        cursor = conn.cursor()

        fiat_symbol = "RUB" if symbol in ["SBER", "GAZP", "LKOH", "YNDX", "TCSG"] else "USDT"
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

            # Математика: вычисляем новую среднюю цену входа
            new_avg_entry = ((asset_balance * avg_entry) + (
                        amount_traded * price)) / new_asset if new_asset > 0 else price

            cursor.execute("UPDATE portfolio SET amount=? WHERE symbol=?", (new_fiat, fiat_symbol))
            if asset_row:
                cursor.execute("UPDATE portfolio SET amount=?, average_entry_price=? WHERE symbol=?",
                               (new_asset, new_avg_entry, symbol))
            else:
                cursor.execute("INSERT INTO portfolio (symbol, amount, average_entry_price) VALUES (?, ?, ?)",
                               (symbol, new_asset, new_avg_entry))
            trade_executed = True

        elif action == "SELL" and asset_balance > 0:
            amount_traded = asset_balance
            gained_fiat = amount_traded * price
            new_fiat = fiat_balance + gained_fiat

            cursor.execute("UPDATE portfolio SET amount=? WHERE symbol=?", (new_fiat, fiat_symbol))
            cursor.execute("UPDATE portfolio SET amount=0, average_entry_price=0 WHERE symbol=?", (symbol,))
            trade_executed = True

        if trade_executed:
            cursor.execute(
                "INSERT INTO trade_history (symbol, action, price, amount, total_value) VALUES (?, ?, ?, ?, ?)",
                (symbol, action, price, amount_traded, amount_traded * price)
            )

        conn.commit()
        conn.close()
        return trade_executed