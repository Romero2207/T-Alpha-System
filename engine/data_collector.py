import time
import sys
import os
import json
import pandas as pd
import requests
import ta
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection, init_db
from ai.gigachat_api import AIEngine
from engine.risk_manager import RiskManager
from engine.portfolio_manager import PortfolioManager
from core.notifier import TelegramNotifier


class GlobalScanner:
    def __init__(self):
        init_db()
        self.ai = AIEngine()
        self.risk_manager = RiskManager()
        self.portfolio = PortfolioManager()
        self.notifier = TelegramNotifier()
        self.bybit = HTTP(testnet=False)
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".ai_config.json")

        # Списки "Голубых фишек" для Низкого риска
        self.blue_chips_crypto = ["BTCUSDT", "ETHUSDT"]
        self.blue_chips_moex = ["SBER", "LKOH", "GAZP", "ROSN", "NVTK", "TCSG", "YDEX"]

    def get_risk_profile(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("risk_profile", "Medium")
        except Exception:
            return "Medium"

    def get_sma_200(self, symbol, market="crypto"):
        """Получает Скользящую среднюю за 200 дней (Глобальный Макро-тренд)"""
        try:
            if market == "crypto":
                res = self.bybit.get_kline(category="linear", symbol=symbol, interval="D", limit=200)
                if res['retCode'] == 0:
                    closes = [float(x[4]) for x in res['result']['list']]
                    if len(closes) < 50: return 0.0
                    return sum(closes) / len(closes)
            else:
                start_date = (datetime.now() - timedelta(days=300)).strftime('%Y-%m-%d')
                url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?iss.meta=off&interval=24&from={start_date}"
                res = requests.get(url, timeout=5).json()
                data = res['candles']['data']
                cols = res['candles']['columns']
                if not data: return 0.0

                idx_close = cols.index('close')
                closes = [float(row[idx_close]) for row in data if row[idx_close] is not None][-200:]
                if len(closes) < 50: return 0.0
                return sum(closes) / len(closes)
        except Exception:
            return 0.0
        return 0.0

    def get_top_volatile_crypto(self, limit=3):
        try:
            res = self.bybit.get_tickers(category="linear")
            if res.get('retCode') != 0: return []

            tickers = res['result']['list']
            hot = []
            for t in tickers:
                symbol = t['symbol']
                if symbol.endswith('USDT') and not symbol.startswith('1000'):
                    turnover = float(t['turnover24h'])
                    change_pct = float(t['price24hPcnt']) * 100
                    price = float(t['lastPrice'])
                    if turnover > 20000000 and abs(change_pct) > 2.0:
                        hot.append({'symbol': symbol, 'price': price, 'change': change_pct, 'volume': turnover,
                                    'market': 'crypto'})
            hot.sort(key=lambda x: abs(x['change']), reverse=True)
            return hot[:limit]
        except Exception:
            return []

    def get_top_volatile_stocks(self, limit=3):
        try:
            url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=marketdata"
            res = requests.get(url, timeout=5).json()
            data = res['marketdata']['data']
            cols = res['marketdata']['columns']

            idx_secid, idx_last, idx_vol, idx_change = cols.index('SECID'), cols.index('LAST'), cols.index(
                'VALTODAY'), cols.index('LASTTOPREVPRICE')

            hot = []
            for row in data:
                symbol, price, vol, change = row[idx_secid], row[idx_last], row[idx_vol], row[idx_change]
                if price and vol and change and vol > 50000000 and abs(change) > 1.5:
                    hot.append({'symbol': symbol, 'price': float(price), 'change': float(change), 'volume': float(vol),
                                'market': 'stocks'})

            hot.sort(key=lambda x: abs(x['change']), reverse=True)
            return hot[:limit]
        except Exception:
            return []

    def get_technical_indicators(self, symbol, market="crypto", window=14):
        try:
            if market == "crypto":
                res = self.bybit.get_kline(category="linear", symbol=symbol, interval=15, limit=window + 30)
                if res['retCode'] == 0:
                    klines = res['result']['list']
                    klines.reverse()
                    df = pd.DataFrame(klines,
                                      columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                else:
                    return None
            else:
                start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
                url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?iss.meta=off&interval=10&from={start_date}"
                res = requests.get(url, timeout=5).json()
                df = pd.DataFrame(res['candles']['data'], columns=res['candles']['columns'])
                if df.empty: return None

            for col in ['open', 'high', 'low', 'close']: df[col] = df[col].astype(float)

            rsi = ta.momentum.RSIIndicator(close=df['close'], window=window).rsi().iloc[-1]
            macd_hist = ta.trend.MACD(close=df['close']).macd_diff().iloc[-1]
            atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'],
                                                 window=14).average_true_range().iloc[-1]

            prev, curr = df.iloc[-2], df.iloc[-1]
            is_bull_engulf = (prev['close'] < prev['open']) and (curr['close'] > curr['open']) and (
                        curr['close'] >= prev['open']) and (curr['open'] <= prev['close'])
            is_bear_engulf = (prev['close'] > prev['open']) and (curr['close'] < curr['open']) and (
                        curr['open'] >= prev['close']) and (curr['close'] <= prev['open'])

            pattern = "Бычье поглощение" if is_bull_engulf else "Медвежье поглощение" if is_bear_engulf else "Нет явного паттерна"

            return {
                "rsi": round(rsi, 2) if not pd.isna(rsi) else 50.0, "macd_hist": round(macd_hist, 6),
                "atr": round(atr, 4), "pattern": pattern
            }
        except Exception:
            return {"rsi": 50.0, "macd_hist": 0, "atr": 0, "pattern": "Нет данных"}

    def run(self):
        print("=" * 50)
        print("СИСТЕМА: ИНТЕЛЛЕКТУАЛЬНЫЙ СКАНЕР С ФИЛЬТРОМ РИСКОВ ЗАПУЩЕН")
        print("=" * 50)

        while True:
            risk_profile = self.get_risk_profile()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛡️ Текущий профиль риска: {risk_profile}")

            targets = self.get_top_volatile_crypto(limit=3) + self.get_top_volatile_stocks(limit=3)

            for asset in targets:
                symbol = asset['symbol']
                price = asset['price']
                change = asset['change']
                market = asset['market']

                self.portfolio.monitor_positions(symbol, price, self.notifier)

                # ==========================================
                # ЛОГИКА НИЗКОГО РИСКА (ГОЛУБЫЕ ФИШКИ + ТРЕНД)
                # ==========================================
                if risk_profile == "Low":
                    # 1. Фильтр мусора (только надежные активы)
                    if symbol not in (self.blue_chips_crypto + self.blue_chips_moex):
                        continue

                    # 2. Фильтр глобального тренда (SMA 200)
                    sma200 = self.get_sma_200(symbol, market)
                    if sma200 > 0 and price < sma200:
                        # Если цена ниже SMA200 - мы в падающем тренде. Игнорируем актив!
                        continue
                # ==========================================

                inds = self.get_technical_indicators(symbol, market=market)
                if not inds: continue

                m_tag = "[CRYPTO]" if market == "crypto" else "[MOEX]"
                state_desc = f"{m_tag} Аномалия: {symbol}. Δ: {change:+.2f}%. Цена: {price}. Индикаторы собраны."

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] {m_tag} {symbol} | RSI: {inds['rsi']} | Паттерн: {inds['pattern']}")

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
                        tp, sl = decision.get('take_profit', 0.0), decision.get('stop_loss', 0.0)
                        trade_ok = self.portfolio.execute_paper_trade(symbol, action, price, tp=tp, sl=sl,
                                                                      reason=decision.get('reason', 'AI Signal'))
                        if trade_ok:
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 АВТОПИЛОТ: Сделка {action} по {symbol} исполнена!")
                            self.notifier.send_signal(symbol, action, price, decision.get('reason', 'Сигнал ИИ'),
                                                      change, tp, sl)

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