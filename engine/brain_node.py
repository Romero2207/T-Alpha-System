import asyncio
import json
import os
import sys
import pandas as pd
import requests
import ta
from pybit.unified_trading import HTTP
from datetime import datetime, timedelta
from typing import Dict, Any

# Подключаем доступ к модулям
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection
from ai.gigachat_api import AIEngine
from engine.risk_manager import RiskManager


class BrainNode:
    def __init__(self, bus):
        self.bus = bus
        self.last_analysis_time = {}
        # Инициализируем настоящий ИИ и Риск-менеджера
        self.ai = AIEngine()
        self.risk_manager = RiskManager()
        self.bybit = HTTP(testnet=False)

    def get_technical_indicators(self, symbol, market="crypto"):
        """Синхронный расчет индикаторов (запускается в фоне)"""
        try:
            if market == "crypto":
                res = self.bybit.get_kline(category="linear", symbol=symbol, interval=15, limit=50)
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
                if not res.get('candles', {}).get('data'): return None
                df = pd.DataFrame(res['candles']['data'], columns=res['candles']['columns'])

            for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)

            rsi = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
            macd_hist = ta.trend.MACD(close=df['close']).macd_diff().iloc[-1]
            atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'],
                                                 window=14).average_true_range().iloc[-1]

            local_high = df['high'].max()
            local_low = df['low'].min()
            prev, curr = df.iloc[-2], df.iloc[-1]
            gap_percent = ((curr['open'] - prev['close']) / prev['close']) * 100

            is_bull = (prev['close'] < prev['open']) and (curr['close'] > curr['open']) and (
                        curr['close'] >= prev['open']) and (curr['open'] <= prev['close'])
            is_bear = (prev['close'] > prev['open']) and (curr['close'] < curr['open']) and (
                        curr['open'] >= prev['close']) and (curr['close'] <= prev['open'])
            pattern = "Бычье поглощение" if is_bull else "Медвежье поглощение" if is_bear else "Нет явного паттерна"

            return {
                "rsi": round(rsi, 2) if not pd.isna(rsi) else 50.0,
                "macd_hist": round(macd_hist, 6),
                "atr": round(atr, 4),
                "local_high": round(local_high, 4),
                "local_low": round(local_low, 4),
                "gap_percent": round(gap_percent, 2),
                "pattern": pattern
            }
        except Exception as e:
            print(f"Ошибка индикаторов {symbol}: {e}")
            return {"rsi": 50.0, "macd_hist": 0, "atr": 0, "local_high": 0, "local_low": 0, "gap_percent": 0.0,
                    "pattern": "Нет данных"}

    async def handle_tick(self, payload: Dict[str, Any]):
        """Асинхронный обработчик тиков"""
        symbol = payload['symbol']
        price = payload['price']
        market = payload.get('market', 'crypto')

        current_time = payload['timestamp']
        last_time = self.last_analysis_time.get(symbol, 0)

        # Анализируем актив раз в 60 секунд
        if current_time - last_time >= 60:
            print(f"🧠 [Brain] Сбор данных и запрос к нейросети для {symbol}...")
            self.last_analysis_time[symbol] = current_time

            loop = asyncio.get_running_loop()

            # 1. Получаем индикаторы в фоновом потоке
            inds = await loop.run_in_executor(None, self.get_technical_indicators, symbol, market)
            if not inds: return

            # 2. Вызываем GigaChat в фоновом потоке (чтобы не блокировать систему)
            decision = await loop.run_in_executor(None, self.ai.analyze_market_state, symbol, price, payload['volume'],
                                                  inds)

            action = decision.get('action', 'HOLD')
            reason = decision.get('reason', 'Анализ завершен')
            confidence = decision.get('confidence', 0)

            # 3. Пропускаем решение через Risk Manager
            approved, rm_reason = self.risk_manager.approve_signal(symbol, action, price, inds['rsi'])

            if not approved and action != "HOLD":
                action = f"HOLD (Блок Риск-менеджера: {action})"
                reason = rm_reason

            signal = {
                "symbol": symbol,
                "action": action,
                "price": price,
                "confidence": confidence,
                "reason": reason
            }

            # 4. Запись мыслей в базу (для сайта)
            state_desc = f"[{market.upper()}] Аномалия: {symbol}. Цена: {price}. Паттерн: {inds['pattern']}"
            await loop.run_in_executor(None, self.save_to_db, state_desc, signal)

            # 5. Отправка сигнала на исполнение
            if "HOLD" not in signal["action"]:
                print(f"⚡ [Brain] ОДОБРЕН БОЕВОЙ СИГНАЛ: {signal['action']} {symbol}")
                await self.bus.publish("TRADE_SIGNAL", signal)

    def save_to_db(self, state_desc, decision):
        """Синхронная функция сохранения в SQLite"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO experience_replay (timestamp, market_state, ai_decision) VALUES (datetime('now', 'localtime'), ?, ?)",
                (state_desc, json.dumps(decision, ensure_ascii=False))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка сохранения логов: {e}")