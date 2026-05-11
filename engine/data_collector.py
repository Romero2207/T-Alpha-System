import time
import sys
import os
import json
import pandas as pd
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
        self.portfolio = PortfolioManager()
        self.bybit = HTTP(testnet=False)
        init_db()

    def get_top_volatile_crypto(self, limit=3):
        """Сканирует ВСЕ монеты на Bybit и выбирает самые активные"""
        try:
            res = self.bybit.get_tickers(category="linear")
            if res['retCode'] != 0: return []

            tickers = res['result']['list']
            hot_assets = []

            for t in tickers:
                symbol = t['symbol']
                # Отсекаем мусор и смотрим только на пары к USDT
                if symbol.endswith('USDT') and not symbol.startswith('1000'):
                    turnover = float(t['turnover24h'])
                    change_pct = float(t['price24hPcnt']) * 100
                    price = float(t['lastPrice'])

                    # Ищем монеты с объемом больше $10 млн и движением > 3%
                    if turnover > 10000000 and abs(change_pct) > 3.0:
                        hot_assets.append({
                            'symbol': symbol,
                            'price': price,
                            'change': change_pct,
                            'volume': turnover
                        })

            hot_assets.sort(key=lambda x: abs(x['change']), reverse=True)
            return hot_assets[:limit]
        except Exception as e:
            print(f"Ошибка сканирования крипторынка: {e}")
            return []

    def get_technical_indicators(self, symbol, window=14):
        """Рассчитывает RSI, MACD, Bollinger Bands и ATR"""
        try:
            res = self.bybit.get_kline(category="linear", symbol=symbol, interval=15, limit=window + 30)
            if res['retCode'] == 0:
                klines = res['result']['list']
                klines.reverse()
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col].astype(float)

                # 1. RSI
                rsi = ta.momentum.RSIIndicator(close=df['close'], window=window).rsi().iloc[-1]

                # 2. MACD
                macd_ind = ta.trend.MACD(close=df['close'])
                macd_hist = macd_ind.macd_diff().iloc[-1]  # Гистограмма MACD

                # 3. Bollinger Bands
                bb_ind = ta.volatility.BollingerBands(close=df['close'])
                bb_high = bb_ind.bollinger_hband().iloc[-1]
                bb_low = bb_ind.bollinger_lband().iloc[-1]

                # 4. ATR (Средняя волатильность)
                atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'],
                                                     window=14).average_true_range().iloc[-1]

                return {
                    "rsi": round(rsi, 2) if not pd.isna(rsi) else 50.0,
                    "macd_hist": round(macd_hist, 6),
                    "bb_high": round(bb_high, 4),
                    "bb_low": round(bb_low, 4),
                    "atr": round(atr, 4)
                }
        except Exception as e:
            pass
        # Значения по умолчанию при ошибке
        return {"rsi": 50.0, "macd_hist": 0, "bb_high": 0, "bb_low": 0, "atr": 0}

    def run(self):
        print("=" * 50)
        print("🚀 СИСТЕМА: ГЛОБАЛЬНЫЙ AI-СКАНЕР ЗАПУЩЕН (УРОВЕНЬ 1: ТРЕНД И ВОЛАТИЛЬНОСТЬ)")
        print("=" * 50)

        while True:
            top_crypto = self.get_top_volatile_crypto(limit=3)

            for asset in top_crypto:
                symbol = asset['symbol']
                price = asset['price']
                change = asset['change']

                # Получаем полный пак индикаторов
                inds = self.get_technical_indicators(symbol)

                state_desc = f"Аномалия: {symbol}. Δ: {change:+.2f}%. Цена: {price}. Индикаторы собраны."
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] РАДАР: {symbol} | RSI: {inds['rsi']} | MACD_H: {inds['macd_hist']} | ATR: {inds['atr']}")

                # Отдаем ИИ цену, объем и ВЕСЬ пак индикаторов
                decision = self.ai.analyze_market_state(symbol, price, asset['volume'], inds)

                decision['market_change'] = round(change, 2)
                decision['current_price'] = price

                action = decision.get('action', 'HOLD')
                if action in ["BUY", "SELL"]:
                    approved, rm_reason = self.risk_manager.approve_signal(symbol, action, price, inds['rsi'])
                    if not approved:
                        decision['action'] = f"HOLD (Blocked: {action})"
                        decision['reason'] = rm_reason
                    else:
                        trade_ok = self.portfolio.execute_paper_trade(symbol, action, price)
                        if trade_ok:
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 АВТОПИЛОТ: Сделка {action} по {symbol} исполнена!")
                        else:
                            decision['action'] = f"HOLD (No Funds for {action})"

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO experience_replay (timestamp, market_state, ai_decision) VALUES (datetime('now', 'localtime'), ?, ?)",
                    (state_desc, json.dumps(decision, ensure_ascii=False))
                )
                conn.commit()
                conn.close()

            time.sleep(60)


if __name__ == "__main__":
    scanner = GlobalScanner()
    scanner.run()