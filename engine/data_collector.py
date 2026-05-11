import time
import sys
import os
import json
import pandas as pd
import requests
import ta
from pybit.unified_trading import HTTP
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection, init_db
from ai.gigachat_api import AIEngine
from engine.risk_manager import RiskManager
from engine.portfolio_manager import PortfolioManager

class GlobalScanner:
    def __init__(self):
        self.ai = AIEngine()
        self.risk_manager = RiskManager()
        self.portfolio = PortfolioManager() # Добавили кошелек
        self.bybit = HTTP(testnet=False)
        init_db()

    def get_top_volatile_crypto(self, limit=3):
        """Сканирует ВСЕ монеты на Bybit и выбирает самые активные (аномалии)"""
        try:
            res = self.bybit.get_tickers(category="linear")
            if res['retCode'] != 0: return []

            tickers = res['result']['list']
            hot_assets = []

            for t in tickers:
                symbol = t['symbol']
                # Берем только USDT пары, без мусорных токенов
                if symbol.endswith('USDT') and not symbol.startswith('1000'):
                    turnover = float(t['turnover24h'])
                    change_pct = float(t['price24hPcnt']) * 100
                    price = float(t['lastPrice'])

                    # Фильтр: Ищем монеты с объемом больше $10 млн, которые сделали сильное движение
                    if turnover > 10000000 and abs(change_pct) > 3.0:
                        hot_assets.append({
                            'symbol': symbol,
                            'price': price,
                            'change': change_pct,
                            'volume': turnover
                        })

            # Сортируем по модулю изменения (самые сильные падения или взлеты)
            hot_assets.sort(key=lambda x: abs(x['change']), reverse=True)
            return hot_assets[:limit]
        except Exception as e:
            print(f"Ошибка сканирования крипторынка: {e}")
            return []

    def get_live_rsi(self, symbol, window=14):
        """Мгновенно качает свежие свечи для расчета RSI горячей монеты"""
        try:
            res = self.bybit.get_kline(category="linear", symbol=symbol, interval=5, limit=window + 5)
            if res['retCode'] == 0:
                klines = res['result']['list']
                klines.reverse()
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df['close'] = df['close'].astype(float)

                rsi_indicator = ta.momentum.RSIIndicator(close=df['close'], window=window)
                current_rsi = rsi_indicator.rsi().iloc[-1]
                return round(current_rsi, 2) if not pd.isna(current_rsi) else 50.0
        except:
            pass
        return 50.0

    def run(self):
        print("=" * 50)
        print("СИСТЕМА: ГЛОБАЛЬНЫЙ AI-СКАНЕР ЗАПУЩЕН")
        print("Радар охватывает 300+ активов. Поиск аномалий...")
        print("=" * 50)

        while True:
            # 1. Сканируем весь рынок одним запросом
            top_crypto = self.get_top_volatile_crypto(limit=3)

            for asset in top_crypto:
                symbol = asset['symbol']
                price = asset['price']
                change = asset['change']

                # 2. Вычисляем математику для найденной аномалии
                rsi = self.get_live_rsi(symbol)
                state_desc = f"Обнаружена аномалия! Актив {symbol}. Изменение за 24ч: {change:+.2f}%. Цена: {price}. RSI: {rsi}."

                print(f"[{datetime.now().strftime('%H:%M:%S')}] РАДАР: {symbol} | Δ: {change:+.2f}% | RSI: {rsi}")

                # 3. Отдаем ИИ на анализ
                decision = self.ai.analyze_market_state(symbol, price, asset['volume'], rsi=rsi)

                # Добавляем данные о рынке в решение для красоты в UI
                decision['market_change'] = round(change, 2)
                decision['current_price'] = price

                # 4. Прогоняем через Риск-Менеджмент
                action = decision.get('action', 'HOLD')
                if action in ["BUY", "SELL"]:
                    approved, rm_reason = self.risk_manager.approve_signal(symbol, action, price, rsi)
                    if not approved:
                        decision['action'] = f"HOLD (Blocked: {action})"
                        decision['reason'] = rm_reason
                    else:
                        # АВТОПИЛОТ В ДЕЙСТВИИ: Если фильтры пройдены, бот торгует сам!
                        trade_ok = self.portfolio.execute_paper_trade(symbol, action, price)
                        if trade_ok:
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 АВТОПИЛОТ: Сделка {action} по {symbol} исполнена!")
                        else:
                            decision['action'] = f"HOLD (No Funds for {action})"

                # 5. Сохраняем в историю (Это прочитает вкладка AI-Скринер в UI)
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO experience_replay (timestamp, market_state, ai_decision) VALUES (datetime('now', 'localtime'), ?, ?)",
                    (state_desc, json.dumps(decision, ensure_ascii=False))
                )
                conn.commit()
                conn.close()

            # Скринер отдыхает 60 секунд перед новым глобальным сканом
            time.sleep(60)


if __name__ == "__main__":
    scanner = GlobalScanner()
    scanner.run()