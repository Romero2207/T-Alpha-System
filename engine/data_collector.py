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
from core.notifier import TelegramNotifier


class GlobalScanner:
    def __init__(self):
        self.ai = AIEngine()
        self.risk_manager = RiskManager()
        self.portfolio = PortfolioManager()
        self.notifier = TelegramNotifier()
        self.bybit = HTTP(testnet=False)
        init_db()

    def get_top_volatile_crypto(self, limit=2):
        """Сканирует Bybit на аномалии"""
        try:
            res = self.bybit.get_tickers(category="linear")
            if res['retCode'] != 0: return []
            tickers = res['result']['list']
            hot = []
            for t in tickers:
                symbol = t['symbol']
                if symbol.endswith('USDT') and not symbol.startswith('1000'):
                    turnover = float(t['turnover24h'])
                    change_pct = float(t['price24hPcnt']) * 100
                    price = float(t['lastPrice'])
                    if turnover > 10000000 and abs(change_pct) > 3.0:
                        hot.append({'symbol': symbol, 'price': price, 'change': change_pct, 'volume': turnover,
                                    'market': 'crypto'})
            hot.sort(key=lambda x: abs(x['change']), reverse=True)
            return hot[:limit]
        except:
            return []

    def get_top_volatile_stocks(self, limit=2):
        """Сканирует всю Мосбиржу (TQBR) на аномалии"""
        try:
            url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=marketdata"
            res = requests.get(url, timeout=5).json()
            data = res['marketdata']['data']
            cols = res['marketdata']['columns']

            idx_secid = cols.index('SECID')
            idx_last = cols.index('LAST')
            idx_vol = cols.index('VALTODAY')
            idx_change = cols.index('LASTTOPREVPRICE')

            hot = []
            for row in data:
                symbol = row[idx_secid]
                price = row[idx_last]
                vol = row[idx_vol]
                change = row[idx_change]

                # Фильтр: есть данные, объем больше 50 млн рублей, движение больше 1.5% (фонда менее волатильна)
                if price and vol and change and vol > 50000000 and abs(change) > 1.5:
                    hot.append({'symbol': symbol, 'price': float(price), 'change': float(change), 'volume': float(vol),
                                'market': 'stocks'})

            hot.sort(key=lambda x: abs(x['change']), reverse=True)
            return hot[:limit]
        except Exception as e:
            print(f"Ошибка MOEX: {e}")
            return []

    def get_technical_indicators(self, symbol, market="crypto", window=14):
        """Универсальный расчет ТА для крипты и акций"""
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
                # Скачиваем историю MOEX для расчета индикаторов
                from datetime import timedelta
                start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
                url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?iss.meta=off&interval=10&from={start_date}"
                res = requests.get(url, timeout=5).json()
                df = pd.DataFrame(res['candles']['data'], columns=res['candles']['columns'])
                if df.empty: return None

            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)

            rsi = ta.momentum.RSIIndicator(close=df['close'], window=window).rsi().iloc[-1]
            macd_hist = ta.trend.MACD(close=df['close']).macd_diff().iloc[-1]
            bb_ind = ta.volatility.BollingerBands(close=df['close'])
            bb_high = bb_ind.bollinger_hband().iloc[-1]
            bb_low = bb_ind.bollinger_lband().iloc[-1]
            atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'],
                                                 window=14).average_true_range().iloc[-1]

            prev, curr = df.iloc[-2], df.iloc[-1]
            is_doji = abs(curr['close'] - curr['open']) <= (curr['high'] - curr['low']) * 0.1
            is_bull_engulf = (prev['close'] < prev['open']) and (curr['close'] > curr['open']) and (
                        curr['close'] >= prev['open']) and (curr['open'] <= prev['close'])
            is_bear_engulf = (prev['close'] > prev['open']) and (curr['close'] < curr['open']) and (
                        curr['open'] >= prev['close']) and (curr['close'] <= prev['open'])

            pattern = "Doji" if is_doji else "Бычье поглощение" if is_bull_engulf else "Медвежье поглощение" if is_bear_engulf else "Нет явного паттерна"

            return {
                "rsi": round(rsi, 2) if not pd.isna(rsi) else 50.0,
                "macd_hist": round(macd_hist, 6), "bb_high": round(bb_high, 4), "bb_low": round(bb_low, 4),
                "atr": round(atr, 4), "pattern": pattern
            }
        except Exception:
            return {"rsi": 50.0, "macd_hist": 0, "bb_high": 0, "bb_low": 0, "atr": 0, "pattern": "Нет данных"}

    def run(self):
        print("=" * 50)
        print("СИСТЕМА: ДВОЙНОЙ ГЛОБАЛЬНЫЙ СКАНЕР (КРИПТА + MOEX) ЗАПУЩЕН")
        print("=" * 50)

        while True:
            # Собираем сливки с обоих рынков
            targets = self.get_top_volatile_crypto(limit=2) + self.get_top_volatile_stocks(limit=2)

            for asset in targets:
                symbol = asset['symbol']
                price = asset['price']
                change = asset['change']
                market = asset['market']

                # 1. Авто-выход (Трейлинг-стопы)
                self.portfolio.monitor_positions(symbol, price, self.notifier)

                # 2. Сбор индикаторов
                inds = self.get_technical_indicators(symbol, market=market)
                if not inds: continue

                # Маркируем рынок для интерфейса [CRYPTO] или [MOEX]
                m_tag = "[CRYPTO]" if market == "crypto" else "[MOEX]"
                state_desc = f"{m_tag} Аномалия: {symbol}. Δ: {change:+.2f}%. Цена: {price}. Индикаторы собраны."

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] {m_tag} {symbol} | RSI: {inds['rsi']} | MACD_H: {inds['macd_hist']} | Паттерн: {inds['pattern']}")

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
                        else:
                            decision['action'] = f"HOLD (No Funds)"

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