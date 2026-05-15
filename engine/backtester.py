import pandas as pd
import ta
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Backtester:
    def __init__(self, initial_balance=1000):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.bybit = HTTP(testnet=False)
        self.trades = []

    def fetch_monthly_data(self, symbol):
        """Загружает около 3000 свечей (15м) для анализа за месяц"""
        all_candles = []
        # Bybit отдает по 200 свечей, нам нужно сделать несколько запросов
        end_time = int(datetime.now().timestamp() * 1000)

        print(f"📥 Загрузка истории для {symbol}...")
        for _ in range(15):  # 15 запросов по 200 свечей = 3000 свечей
            res = self.bybit.get_kline(category="linear", symbol=symbol, interval=15, end=end_time, limit=200)
            if res['retCode'] == 0:
                candles = res['result']['list']
                if not candles: break
                all_candles.extend(candles)
                # Сдвигаем время назад для следующего запроса
                end_time = int(candles[-1][0]) - 1
            else:
                break

        df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
        df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')
        df = df.sort_values('ts').reset_index(drop=True)
        for col in ['open', 'high', 'low', 'close', 'vol']:
            df[col] = df[col].astype(float)
        return df

    def run_test(self, symbol):
        df = self.fetch_monthly_data(symbol)
        if df.empty: return

        # Считаем индикаторы для всей истории сразу
        df['rsi'] = ta.momentum.RSIIndicator(df['close']).rsi()
        macd = ta.trend.MACD(df['close'])
        df['macd_h'] = macd.macd_diff()

        in_position = False
        entry_price = 0

        print(f"🚀 Начало теста для {symbol}...")

        for i in range(15, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]

            # Логика входа (копия нашего ИИ)
            # Бычье поглощение + RSI < 40
            is_bull_engulf = (prev['close'] < prev['open']) and (row['close'] > row['open']) and (
                        row['close'] >= prev['open'])

            if not in_position and row['rsi'] < 35 and is_bull_engulf:
                in_position = True
                entry_price = row['close']
                self.trades.append({'type': 'BUY', 'price': entry_price, 'ts': row['ts']})

            # Логика выхода (Тейк +3% или Стоп -1.5% или RSI > 70)
            elif in_position:
                profit_pct = (row['close'] - entry_price) / entry_price * 100
                if profit_pct >= 3.0 or profit_pct <= -1.5 or row['rsi'] > 70:
                    in_position = False
                    self.trades.append({'type': 'SELL', 'price': row['close'], 'ts': row['ts'], 'pnl': profit_pct})
                    self.balance *= (1 + profit_pct / 100)

        self.display_results(symbol)

    def display_results(self, symbol):
        win_trades = [t for t in self.trades if t.get('pnl', 0) > 0]
        winrate = (len(win_trades) / (len(self.trades) / 2)) * 100 if self.trades else 0
        total_pnl = self.balance - self.initial_balance

        print(f"\n--- РЕЗУЛЬТАТЫ ТЕСТА: {symbol} ---")
        print(f"💰 Итоговый баланс: ${self.balance:.2f}")
        print(f"📈 Чистая прибыль: ${total_pnl:.2f} ({(total_pnl / self.initial_balance) * 100 :.2f}%)")
        print(f"📊 Всего сделок: {len(self.trades) // 2}")
        print(f"🎯 Winrate: {winrate:.2f}%")
        print("-------------------------------\n")


if __name__ == "__main__":
    tester = Backtester(initial_balance=1000)

    # Корзина для тестирования (Биткоин + топовые Альткоины)
    portfolio = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]

    print("🌐 НАЧИНАЕМ МАССОВЫЙ БЭКТЕСТ ПОРТФЕЛЯ...")
    for coin in portfolio:
        tester.run_test(coin)

    total_profit = tester.balance - tester.initial_balance
    print("\n" + "=" * 40)
    print("🏆 ИТОГОВЫЙ РЕЗУЛЬТАТ ПОРТФЕЛЯ ЗА МЕСЯЦ 🏆")
    print("=" * 40)
    print(f"💵 Стартовый капитал: $1000.00")
    print(f"💰 Финальный капитал: ${tester.balance:.2f}")
    print(f"🚀 ЧИСТАЯ ПРИБЫЛЬ: ${total_profit:.2f} ({(total_profit / 1000) * 100 :.2f}%)")
    print("=" * 40)