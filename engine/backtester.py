import pandas as pd
import ta
from pybit.unified_trading import HTTP
from datetime import datetime
import sys
import os
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Backtester:
    def __init__(self, initial_balance=1000):
        self.initial_balance = initial_balance
        self.bybit = HTTP(testnet=False)
        self.total_portfolio_profit = 0

    def fetch_monthly_data(self, symbol):
        """Загружает свечи (15м для крипты, 10м для MOEX) для анализа за прошлый месяц"""
        all_candles = []

        # 🪙 ЛОГИКА ДЛЯ КРИПТОВАЛЮТЫ (BYBIT)
        if "USDT" in symbol:
            end_time = int(datetime.now().timestamp() * 1000)
            for _ in range(15):
                res = self.bybit.get_kline(category="linear", symbol=symbol, interval=15, end=end_time, limit=200)
                if res['retCode'] == 0:
                    candles = res['result']['list']
                    if not candles: break
                    all_candles.extend(candles)
                    end_time = int(candles[-1][0]) - 1
                else:
                    break
            df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
            df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')

        # 🏛️ ЛОГИКА ДЛЯ ФОНДОВОГО РЫНКА (MOEX)
        else:
            from datetime import timedelta
            # Берем историю за последние 30 дней
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            # Запрашиваем 10-минутные свечи (интервал 10)
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?interval=10&from={start_date}"

            try:
                res = requests.get(url, timeout=5).json()
                candles = res.get('candles', {}).get('data', [])
                if not candles: return pd.DataFrame()

                df = pd.DataFrame(candles, columns=res['candles']['columns'])
                df = df.rename(columns={'begin': 'ts', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                                        'volume': 'vol'})
                df['ts'] = pd.to_datetime(df['ts'])
            except Exception as e:
                print(f"Ошибка загрузки данных MOEX для {symbol}: {e}")
                return pd.DataFrame()

        # Универсальная сортировка и типизация
        df = df.sort_values('ts').reset_index(drop=True)
        for col in ['open', 'high', 'low', 'close', 'vol']:
            df[col] = df[col].astype(float)

        # Удаляем битые свечи (где нет цены закрытия)
        df = df.dropna(subset=['close'])

        return df

    def run_test(self, symbol, coin_budget):
        df = self.fetch_monthly_data(symbol)
        if df.empty: return

        # 🧠 Рассчитываем индикаторы ИМЕННО ТАК, как мы прописали в GigaChat
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_low'] = bb.bollinger_lband()
        df['bb_high'] = bb.bollinger_hband()
        df['sma200'] = df['close'].rolling(window=200).mean()

        in_position = False
        entry_price = 0
        trades = []
        balance = coin_budget

        print(f"🚀 Тест стратегии GigaChat для {symbol} (Бюджет: ${coin_budget:.2f})...")

        # Начинаем с 200 свечи, чтобы успела рассчитаться скользящая средняя (SMA200)
        for i in range(200, len(df)):
            row = df.iloc[i]

            # 🟢 ЛОГИКА ВХОДА (Как в нашем новом Промпте)
            if not in_position:
                # Агрессивная покупка: RSI < 35 ИЛИ цена пробила нижний Боллинджер
                if row['rsi'] < 35 or row['close'] <= row['bb_low']:
                    in_position = True
                    entry_price = row['close']
                    trades.append({'type': 'BUY', 'price': entry_price, 'ts': row['ts']})

            # 🔴 ЛОГИКА ВЫХОДА (Тейк-профит, Стоп-лосс или Перегрев)
            elif in_position:
                profit_pct = (row['close'] - entry_price) / entry_price * 100

                # Тейк +2.5%, Стоп -1.5%, или выход по Боллинджеру/RSI
                if profit_pct >= 2.5 or profit_pct <= -1.5 or row['rsi'] > 68 or row['close'] >= row['bb_high']:
                    in_position = False
                    trades.append({'type': 'SELL', 'price': row['close'], 'ts': row['ts'], 'pnl': profit_pct})
                    # Сложный процент в рамках одной монеты
                    balance *= (1 + profit_pct / 100)

        # Подводим итоги конкретной монеты
        win_trades = [t for t in trades if t.get('pnl', 0) > 0]
        winrate = (len(win_trades) / (len(trades) / 2)) * 100 if len(trades) > 1 else 0
        coin_profit = balance - coin_budget
        self.total_portfolio_profit += coin_profit

        print(f"  └ 📈 Прибыль: ${coin_profit:.2f} | 🎯 Winrate: {winrate:.0f}% | 📊 Сделок: {len(trades) // 2}")


if __name__ == "__main__":
    initial_cap = 1000
    tester = Backtester(initial_balance=initial_cap)

    # Тестируем на топовых акциях Мосбиржи
    portfolio = ["SBER", "LKOH", "GAZP", "YDEX", "T"]  # Сбер, Лукойл, Газпром, Яндекс, Т-Банк
    coin_budget = initial_cap / len(portfolio)  # Выделяем по 200$ на акцию (или 20,000 руб, суть та же)

    print(f"🌐 НАЧИНАЕМ БЭКТЕСТ (Стартовый капитал: ${initial_cap})\n")

    for coin in portfolio:
        tester.run_test(coin, coin_budget)

    print("\n" + "=" * 45)
    print("🏆 ИТОГОВЫЙ РЕЗУЛЬТАТ ПОРТФЕЛЯ ЗА МЕСЯЦ 🏆")
    print("=" * 45)
    print(f"💵 Стартовый капитал: ${initial_cap:.2f}")
    print(f"💰 Финальный капитал: ${(initial_cap + tester.total_portfolio_profit):.2f}")
    print(
        f"🚀 ЧИСТАЯ ПРИБЫЛЬ: ${tester.total_portfolio_profit:.2f} ({(tester.total_portfolio_profit / initial_cap) * 100 :.2f}%)")
    print("=" * 45)