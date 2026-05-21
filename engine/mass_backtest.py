import pandas as pd
import ta
import time
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
import concurrent.futures

# Отключаем предупреждения Pandas для чистоты консоли
pd.options.mode.chained_assignment = None


class MassBacktester:
    def __init__(self):
        self.bybit = HTTP(testnet=False)
        self.days_to_test = 30  # Тестируем за последние 30 дней

    def get_all_usdt_pairs(self):
        """Получаем список всех USDT фьючерсов"""
        print("🔍 Запрашиваю список всех монет на Bybit...")
        res = self.bybit.get_instruments_info(category="linear")
        symbols = [x['symbol'] for x in res['result']['list']
                   if x['quoteCoin'] == 'USDT' and x['status'] == 'Trading'
                   and not x['symbol'].startswith('1000')]  # Убираем шиткоины с нулями
        print(f"✅ Найдено {len(symbols)} торговых пар. Запуск мультипоточного анализа...\n")
        return symbols

    def fetch_data_and_test(self, symbol):
        """Скачивает данные и прогоняет стратегию для ОДНОЙ монеты"""
        try:
            # 1. Скачиваем данные (Берем 1-часовые свечи для быстроты и сглаживания шума)
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = int((datetime.now() - timedelta(days=self.days_to_test)).timestamp() * 1000)

            res = self.bybit.get_kline(category="linear", symbol=symbol, interval=60, start=start_time, end=end_time,
                                       limit=1000)
            if res['retCode'] != 0 or not res['result']['list']:
                return None

            candles = res['result']['list']
            candles.reverse()  # Разворачиваем хронологию

            df = pd.DataFrame(candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
            for col in ['close', 'low', 'high']: df[col] = df[col].astype(float)

            # 2. Считаем индикаторы (Логика нашего Промпта)
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
            bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
            df['bb_low'] = bb.bollinger_lband()

            # 3. Эмуляция торгов
            in_position = False
            entry_price = 0
            trades = 0
            wins = 0
            balance = 200  # Виртуальные 200$ на монету
            leverage = 1  # Плечо х2 как в промпте

            for i in range(50, len(df)):
                row = df.iloc[i]

                if not in_position:
                    # Условие входа (Агрессивно)
                    if row['rsi'] < 35 or row['close'] <= row['bb_low']:
                        in_position = True
                        entry_price = row['close']
                else:
                    # Считаем профит с учетом плеча х2
                    price_change_pct = (row['close'] - entry_price) / entry_price * 100
                    pnl_pct = price_change_pct * leverage

                    # Жесткие выходы из промпта
                    if pnl_pct >= 1.5 or pnl_pct <= -1.0 or row['rsi'] > 68:
                        in_position = False
                        trades += 1
                        balance *= (1 + pnl_pct / 100)
                        if pnl_pct > 0: wins += 1

            if trades == 0: return None

            winrate = (wins / trades) * 100
            profit = balance - 200

            return {
                "symbol": symbol,
                "profit_usd": profit,
                "winrate": winrate,
                "trades": trades
            }
        except Exception:
            return None

    def run_mass_test(self):
        symbols = self.get_all_usdt_pairs()
        results = []

        # МАГИЯ ЗДЕСЬ: Запускаем скачивание и расчеты в 20 потоков одновременно!
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(self.fetch_data_and_test, sym): sym for sym in symbols}

            # Полоса загрузки (выводим прогресс)
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                res = future.result()
                if res: results.append(res)
                print(f"🔄 Обработано: {completed}/{len(symbols)} монет...", end='\r')

        print(f"\n\n⏱️ Анализ {len(symbols)} рынков завершен за {round(time.time() - start_time, 1)} секунд!")

        # Фильтруем и сортируем ТОП-10 лучших монет
        df_res = pd.DataFrame(results)
        df_res = df_res[df_res['trades'] >= 5]  # Отсекаем те, где было мало сделок
        top_10 = df_res.sort_values(by='profit_usd', ascending=False).head(10)

        # --- НОВЫЙ БЛОК: СОХРАНЯЕМ ОПЫТ ДЛЯ ИИ ---
        import json
        experience_db = {}
        for _, row in df_res.iterrows():
            experience_db[row['symbol']] = {
                "winrate": round(row['winrate'], 1),
                "profit": round(row['profit_usd'], 1),
                "trades": row['trades']
            }
        with open("ai_experience.json", "w") as f:
            json.dump(experience_db, f)
        print("🧠 [Memory] Опыт успешно загружен в нейронную базу (ai_experience.json)!")

        print("\n" + "=" * 50)
        print("🏆 ТОП-10 ЛУЧШИХ МОНЕТ ДЛЯ НАШЕГО ИИ 🏆")
        print("=" * 50)
        for _, row in top_10.iterrows():
            print(
                f"🪙 {row['symbol']:<10} | 💵 Профит: ${row['profit_usd']:>7.2f} | 🎯 Winrate: {row['winrate']:>5.1f}% | 📊 Сделок: {row['trades']}")
        print("=" * 50)


if __name__ == "__main__":
    tester = MassBacktester()
    tester.run_mass_test()