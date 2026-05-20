import asyncio
import time
import os
import sys
import pandas as pd
import numpy as np
import ta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from pybit.unified_trading import HTTP
import requests
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection

app = FastAPI()
system_bus = None
bybit_client = HTTP(testnet=False)


# ИСПРАВЛЕНИЕ: Вместо жесткого пула делаем динамический эндпоинт для ВСЕХ бумаг
@app.get("/api/assets/{market}")
async def get_all_assets(market: str):
    try:
        if market == "crypto":
            # Запрашиваем вообще все линейные USDT пары с Bybit
            res = bybit_client.get_instruments_info(category="linear")
            if res['retCode'] == 0:
                symbols = sorted([x['symbol'] for x in res['result']['list'] if
                                  x['quoteCoin'] == 'USDT' and not x['symbol'].startswith('1000')])
                return {"status": "ok", "data": symbols}
        else:
            # Запрашиваем абсолютно все акции с главного режима торгов Мосбиржи (TQBR)
            url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=securities"
            res = requests.get(url, timeout=5).json()
            symbols = sorted([x[0] for x in res['securities']['data']])
            return {"status": "ok", "data": symbols}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "error", "data": []}


@app.get("/api/portfolio")
async def get_portfolio():
    try:
        conn = get_connection()
        p_df = pd.read_sql_query("SELECT symbol, amount, average_entry_price FROM portfolio WHERE amount > 0", conn)
        # ИСПРАВЛЕНИЕ: Добавили выборку поля 'amount' (объем сделки) из истории
        h_df = pd.read_sql_query("SELECT timestamp, symbol, action, price, amount, total_value FROM trade_history ORDER BY id DESC LIMIT 20", conn)
        conn.close()

        fiat = p_df[p_df['symbol'].isin(['USDT', 'RUB'])].to_dict('records')

        assets = []
        for _, row in p_df[~p_df['symbol'].isin(['USDT', 'RUB'])].iterrows():
            sym = row['symbol']
            entry = row['average_entry_price']
            amt = row['amount']
            live_price = entry

            try:
                if "USDT" in sym:
                    res = bybit_client.get_tickers(category="linear", symbol=sym)
                    live_price = float(res['result']['list'][0]['lastPrice'])
                else:
                    url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{sym}.json?iss.only=marketdata"
                    res = requests.get(url, timeout=2).json()
                    live_price = float(res['marketdata']['data'][0][res['marketdata']['columns'].index('LAST')] or entry)
            except: pass

            pnl = (live_price - entry) * amt
            pnl_pct = ((live_price - entry) / entry) * 100 if entry > 0 else 0

            assets.append({
                "symbol": sym, "amount": amt, "entry": entry,
                "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)
            })

        return {"status": "ok", "fiat": fiat, "assets": assets, "history": h_df.to_dict('records')}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/logs")
async def get_logs():
    """Подтягиваем мысли ИИ из базы данных"""
    try:
        conn = get_connection()
        # Берем последние 30 записей логов
        df = pd.read_sql_query(
            "SELECT timestamp, market_state, ai_decision FROM experience_replay ORDER BY id DESC LIMIT 30", conn)
        conn.close()

        logs = []
        for _, row in df.iterrows():
            try:
                dec = json.loads(row['ai_decision'])
                # Парсим название тикера из строки market_state
                state_text = row['market_state']
                symbol = state_text.split('Аномалия: ')[1].split('.')[
                    0].strip() if 'Аномалия:' in state_text else 'Анализ'

                logs.append({
                    "time": row['timestamp'].split(' ')[1],
                    "symbol": symbol,
                    "state": state_text,
                    "action": dec.get("action", "HOLD"),
                    "reason": dec.get("reason", "Анализ рынка..."),
                    "conf": dec.get("confidence", 0),
                    "sl": dec.get("sl", 0),  #
                    "tp": dec.get("tp", 0)  #
                })
            except:
                pass
        return {"status": "ok", "data": logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/settings")
async def get_settings():
    """Отдаем текущие настройки риска фронтенду при обновлении страницы"""
    try:
        if os.path.exists("settings.json"):
            with open("settings.json", "r") as f:
                return json.load(f)
    except: pass
    return {"crypto": "low", "moex": "low"}

@app.get("/api/history/{symbol}")
async def get_history(symbol: str):
    try:
        if "USDT" in symbol:
            res = bybit_client.get_kline(category="linear", symbol=symbol, interval="15", limit=200)
            if res['retCode'] != 0: return {"status": "error"}
            klines = res['result']['list']
            klines.reverse()
            df = pd.DataFrame(klines, columns=['ts', 'o', 'h', 'l', 'c', 'v', 't'])
            df['ts'] = pd.to_numeric(df['ts'])
        else:
            from datetime import datetime, timedelta
            # Запрашиваем историю только за последние 14 дней, чтобы не получать цены 2014 года
            start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?interval=10&from={start_date}"
            res = requests.get(url, timeout=5).json()
            candles = res.get('candles', {}).get('data', [])
            if not candles: return {"status": "error"}
            # Оставляем только свежие 200 свечей, если их пришло больше
            candles = candles[-200:]
            df = pd.DataFrame(candles, columns=res['candles']['columns'])
            df = df.rename(columns={'begin': 'ts', 'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
            df['ts'] = df['ts'].apply(lambda x: int(time.mktime(time.strptime(x, "%Y-%m-%d %H:%M:%S"))) * 1000)

        for col in ['o', 'h', 'l', 'c', 'v']: df[col] = df[col].astype(float)
        df = df.dropna(subset=['c'])  # ИСПРАВЛЕНИЕ: Удаляем битые свечи (починит Лукойл)

        # Форматируем время сразу в читаемый вид для категориальной оси X
        time_strings = [time.strftime('%d.%m %H:%M', time.localtime(ts / 1000)) for ts in df['ts']]

        current_price = df['c'].iloc[-1]
        rsi = ta.momentum.RSIIndicator(df['c'], window=14).rsi().iloc[-1]
        sma200 = df['c'].rolling(200).mean().iloc[-1] if len(df) >= 200 else df['c'].mean()
        # Новые индикаторы: Полосы Боллинджера
        bb = ta.volatility.BollingerBands(close=df['c'], window=20, window_dev=2)
        bb_high = [x if pd.notna(x) else None for x in bb.bollinger_hband().tolist()]
        bb_low = [x if pd.notna(x) else None for x in bb.bollinger_lband().tolist()]

        min_p, max_p = df['l'].min(), df['h'].max()
        bins = np.linspace(min_p, max_p, 40)
        df['typ_price'] = (df['h'] + df['l'] + df['c']) / 3
        df['bin'] = pd.cut(df['typ_price'], bins=bins)
        vol_profile = df.groupby('bin', observed=False)['v'].sum().reset_index()
        vol_profile['mid'] = vol_profile['bin'].apply(lambda x: x.mid)
        poc_idx = vol_profile['v'].idxmax()
        poc_price = float(vol_profile.loc[poc_idx, 'mid'])

        levels = []
        high_vol_nodes = vol_profile[vol_profile['v'] > vol_profile['v'].mean() * 1.5]
        for _, row in high_vol_nodes.iterrows():
            if abs(float(row['mid']) - poc_price) > (max_p - min_p) * 0.04:
                levels.append({"price": float(row['mid']),
                               "type": "resistance" if float(row['mid']) > current_price else "support"})

        # Форматируем время в ISO для Plotly, чтобы не ломалась ось X
        time_strings = [time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts / 1000)) for ts in df['ts']]

        data = {
            "time": time_strings, "open": df['o'].tolist(), "high": df['h'].tolist(),
            "low": df['l'].tolist(), "close": df['c'].tolist(),
            "poc": poc_price, "levels": levels,
            "rsi": round(rsi, 2) if not pd.isna(rsi) else 50,
            "sma": round(sma200, 2),
            "bb_high": bb_high,  # Добавили верхнюю границу
            "bb_low": bb_low  # Добавили нижнюю границу
        }
        # ИСПРАВЛЕНИЕ: Жесткая синхронизация цен (подклеиваем настоящий live-ценник к истории свечей)
        if "USDT" in symbol:
            ticker_res = bybit_client.get_tickers(category="linear", symbol=symbol)
            if ticker_res['retCode'] == 0:
                current_price = float(ticker_res['result']['list'][0]['lastPrice'])
                df.loc[df.index[-1], 'c'] = current_price  # Корректируем последнюю точку истории
        else:
            url_ticker = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}.json?iss.only=marketdata"
            ticker_res = requests.get(url_ticker, timeout=2).json()
            if 'marketdata' in ticker_res and ticker_res['marketdata']['data']:
                cols_m = ticker_res['marketdata']['columns']
                row_m = ticker_res['marketdata']['data'][0]
                current_price = float(row_m[cols_m.index('LAST')] or row_m[cols_m.index('WAPRICE')] or current_price)
                df.loc[df.index[-1], 'c'] = current_price
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>T-Alpha Pro | Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        :root { --bg: #0B0E14; --panel: #161A25; --text: #848E9C; --accent: #F3BA2F; --green: #0ECB81; --red: #F6465D; border-color: #2B3139; }
        body { margin: 0; background-color: var(--bg); color: #EAECEF; font-family: 'Segoe UI', sans-serif; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

        .header { background-color: var(--panel); border-bottom: 1px solid var(--border-color); padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; }
        .status { font-size: 0.9rem; color: var(--green); }

        /* Табы (Вкладки) */
        .tabs { display: flex; background: var(--panel); border-bottom: 1px solid var(--border-color); padding: 0 20px; }
        .tab-btn { background: transparent; border: none; color: var(--text); padding: 15px 20px; cursor: pointer; font-size: 1rem; font-weight: bold; border-bottom: 2px solid transparent; transition: 0.2s; }
        .tab-btn:hover { color: #fff; }
        .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }

        .tab-content { display: none !important; }
        .tab-content.active { display: flex !important; flex-direction: column; gap: 15px; flex: 1; padding: 15px; overflow-y: auto; }

        .panel { background-color: var(--panel); border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; }
        .panel-title { font-weight: bold; margin-bottom: 15px; color: #fff; border-bottom: 1px solid var(--border-color); padding-bottom: 10px;}

        /* Сетка для дашборда */
        .dash-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }
        th { color: var(--text); font-weight: normal; }

        /* Торговый терминал */
        .trade-layout { display: flex; gap: 15px; height: calc(100vh - 140px); }
        .trade-main { flex: 3; display: flex; flex-direction: column; }
        .trade-side { flex: 1; display: flex; flex-direction: column; gap: 15px; }

        .ticker-selector { display: flex; gap: 10px; margin-bottom: 10px; }
        select { background: var(--bg); color: #fff; border: 1px solid var(--border-color); padding: 8px; border-radius: 4px; font-size: 1rem; width: 100%;}

        #tvchart { flex: 1; width: 100%; background: var(--bg); border: 1px solid var(--border-color); border-radius: 8px;}

        /* Логи ИИ */
        .log-container { flex: 1; overflow-y: auto; }
        .log-card { background: rgba(255,255,255,0.03); border-left: 3px solid #555; padding: 10px; margin-bottom: 8px; border-radius: 4px; font-size: 0.85rem; }
        .buy { border-color: var(--green); } .sell { border-color: var(--red); }

        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: #2B3139; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="header">
        <h2 style="margin:0; color:var(--accent);">⚡ T-Alpha Pro</h2>
        <div class="status" id="conn-status">Синхронизация...</div>
    </div>

    <div class="tabs">
        <button class="tab-btn active" onclick="openTab('tab-dashboard', this)">Обзор Портфеля</button>
        <button class="tab-btn" onclick="openTab('tab-trade', this); setTimeout(() => window.dispatchEvent(new Event('resize')), 100);">Торговый Терминал</button>
        <button class="tab-btn" onclick="openTab('tab-ai', this)">Управление ИИ</button>
    </div>

    <div id="tab-dashboard" class="tab-content active">
        <div class="dash-grid">
            <div class="panel">
                <div class="panel-title" style="color: #F3BA2F;">🪙 Портфель: Криптовалюта</div>
                <div style="font-size: 1.2rem; margin-bottom: 10px;">Свободно: <strong id="bal-usdt" style="color:#fff;">$0.00</strong></div>
                <table id="crypto-assets"><tr><th>Токен</th><th>Объем</th><th>Цена входа</th><th>PnL</th></tr></table>
                <div style="margin-top: 20px; font-weight: bold; color:#848E9C; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 5px;">📜 Журнал ордеров Крипты:</div>
                <table id="crypto-history"></table>
            </div>
            <div class="panel">
                <div class="panel-title" style="color: #0ECB81;">🏛️ Портфель: Московская Биржа</div>
                <div style="font-size: 1.2rem; margin-bottom: 10px;">Свободно: <strong id="bal-rub" style="color:#fff;">0.00 ₽</strong></div>
                <table id="moex-assets"><tr><th>Акция</th><th>Объем</th><th>Цена входа</th><th>PnL</th></tr></table>
                <div style="margin-top: 20px; font-weight: bold; color:#848E9C; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 5px;">📜 Журнал ордеров MOEX:</div>
                <table id="moex-history"></table>
            </div>
        </div>
    </div>

    <div id="tab-trade" class="tab-content">
        <div class="ticker-selector" style="align-items: center; gap: 8px; position: relative;">
            <select id="market-select" onchange="changeMarket(this.value)" style="flex: 1;">
                <option value="crypto">🪙 Крипторынок (Bybit)</option>
                <option value="moex">🏛️ Фондовый рынок (MOEX)</option>
            </select>
            <select id="symbol-select" onchange="changeSymbol(this.value)" style="flex: 2;">
                <option>Загрузка полного пула активов...</option>
            </select>

            <button id="fav-btn" onclick="toggleFavorite()" style="background: transparent; border: 1px solid var(--border-color); color: var(--text); padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 1.2rem; transition: 0.2s;">⭐</button>
            <button onclick="toggleWatchlistModal()" style="background: var(--panel); border: 1px solid var(--border-color); color: #fff; padding: 8px 12px; border-radius: 4px; cursor: pointer;">📑 Мой список</button>

            <div id="watchlist-modal" style="display:none; position: absolute; top: 50px; right: 0; background: #1e222d; border: 1px solid var(--border-color); border-radius: 8px; width: 280px; max-height: 400px; overflow-y: auto; z-index: 1000; padding: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);">
                <div style="color: #F3BA2F; font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 5px;">🪙 Криптовалюта</div>
                <div id="wl-crypto" style="display: flex; flex-direction: column; gap: 4px; margin-bottom: 15px;"></div>

                <div style="color: #0ECB81; font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid #333; padding-bottom: 5px;">🏛️ Фондовый рынок</div>
                <div id="wl-moex" style="display: flex; flex-direction: column; gap: 4px;"></div>
            </div>
        </div>

        <div class="trade-layout">
            <div class="trade-main">
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:5px;">
                    <h2 style="margin:0;" id="active-symbol">BTCUSDT</h2>
                    <h2 style="margin:0; font-family:monospace; color:var(--accent);" id="active-price">...</h2>
                </div>
                <div id="tvchart"></div>
            </div>

            <div class="trade-side">
                <div class="panel">
                    <div class="panel-title">🔍 X-Ray Анализ</div>
                    <div style="margin-bottom:10px;">RSI (14): <strong id="xray-rsi">--</strong> <span id="xray-rsi-verdict"></span></div>
                    <div style="margin-bottom:10px;">Тренд (SMA200): <strong id="xray-sma">--</strong></div>
                    <div>База (POC): <strong id="xray-poc" style="color:var(--accent);">--</strong></div>
                </div>
                <div class="panel" style="flex:1; display:flex; flex-direction:column;">
                    <div class="panel-title">🧠 Быстрые Сигналы</div>
                    <div class="log-container" id="ai-logs-mini"></div>
                </div>
            </div>
        </div>
    </div>

    <div id="tab-ai" class="tab-content">
        <div class="dash-grid">
            <div class="panel">
                <div class="panel-title">⚙️ Настройки Риск-Менеджмента</div>
                <div style="margin-bottom: 20px;">
                    <label style="color:var(--text);">Стратегия Крипторынка:</label><br>
                    <select id="setting-crypto" style="margin-top:5px; width: 100%; padding: 8px; background: var(--bg); color: #fff; border: 1px solid var(--border-color); border-radius: 4px;">
                        <option value="low">Low Risk (Безопасно, покупка до RSI 65)</option>
                        <option value="medium">Medium Risk (Агрессивно, покупка до RSI 75)</option>
                    </select>
                </div>
                <div>
                    <label style="color:var(--text);">Стратегия Фондового рынка:</label><br>
                    <select id="setting-moex" style="margin-top:5px; width: 100%; padding: 8px; background: var(--bg); color: #fff; border: 1px solid var(--border-color); border-radius: 4px;">
                        <option value="low">Low Risk (Безопасно, покупка до RSI 65)</option>
                        <option value="medium">Medium Risk (Агрессивно, покупка до RSI 75)</option>
                    </select>
                </div>
                <button onclick="saveSettings(this)" style="margin-top: 20px; padding: 10px; background:var(--accent); color:#000; border:none; border-radius:4px; font-weight:bold; cursor:pointer; transition: 0.3s;">Сохранить настройки</button>
            </div>

            <div class="panel" style="height: calc(100vh - 200px); display:flex; flex-direction:column;">
                <div class="panel-title">🧠 Подробный Журнал Мыслей ИИ</div>
                <div class="log-container" id="ai-logs-full"></div>
            </div>
        </div>
    </div>

    <script>
        let currentMarket = "crypto";
        let currentSymbol = "BTCUSDT"; 
        let favorites = JSON.parse(localStorage.getItem('t_alpha_favs')) || ["BTCUSDT", "SBER"];

        // Умное переключение вкладок с сохранением их внутреннего дизайна
        function openTab(tabId, btn) {
            document.querySelectorAll('.tab-content').forEach(t => {
                t.classList.remove('active');
                t.style.display = 'none';
            });
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

            const activeTab = document.getElementById(tabId);
            activeTab.classList.add('active');
            btn.classList.add('active');

            if (tabId === 'tab-dashboard') {
                activeTab.style.setProperty('display', 'grid', 'important');
            } else {
                activeTab.style.setProperty('display', 'flex', 'important');
            }
        }

        function saveSettings(btn) {
            const cryptoMode = document.getElementById('setting-crypto').value;
            const moexMode = document.getElementById('setting-moex').value;

            fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({crypto: cryptoMode, moex: moexMode})
            }).then(res => res.json()).then(data => {
                if (data.status === 'ok') {
                    btn.style.background = '#0ECB81';
                    btn.style.color = '#fff';
                    btn.innerText = '✅ Настройки применены!';
                    setTimeout(() => {
                        btn.style.background = 'var(--accent)';
                        btn.style.color = '#000';
                        btn.innerText = 'Сохранить настройки';
                    }, 2000);
                }
            });
        }

        async function loadSettingsUI() {
            try {
                const res = await fetch('/api/settings');
                const data = await res.json();
                if (data.crypto) document.getElementById('setting-crypto').value = data.crypto;
                if (data.moex) document.getElementById('setting-moex').value = data.moex;
            } catch (e) {}
        }

        // Динамическая загрузка ВСЕГО пула активов с бэкенда
        async function changeMarket(market) {
            currentMarket = market;
            const select = document.getElementById('symbol-select');
            select.innerHTML = "<option>Синхронизация пула бумаг...</option>";

            try {
                const response = await fetch(`/api/assets/${market}`);
                const result = await response.json();

                if (result.status === "ok") {
                    select.innerHTML = "";
                    result.data.forEach(t => {
                        let opt = document.createElement('option');
                        opt.value = t; opt.innerHTML = t;
                        if(t === currentSymbol) opt.selected = true;
                        select.appendChild(opt);
                    });

                    if (!result.data.includes(currentSymbol)) {
                        changeSymbol(result.data[0]);
                    }
                }
            } catch (e) {
                select.innerHTML = "<option>Ошибка загрузки пула</option>";
            }
            renderWatchlist();
        }

        function toggleWatchlistModal() {
            const modal = document.getElementById('watchlist-modal');
            modal.style.display = modal.style.display === 'none' ? 'block' : 'none';
        }

        function toggleFavorite() {
            const index = favorites.indexOf(currentSymbol);
            if (index === -1) {
                favorites.push(currentSymbol);
            } else {
                favorites.splice(index, 1);
            }
            localStorage.setItem('t_alpha_favs', JSON.stringify(favorites));
            renderWatchlist();
        }

        function renderWatchlist() {
            const c_container = document.getElementById('wl-crypto');
            const m_container = document.getElementById('wl-moex');
            const btn = document.getElementById('fav-btn');
            if(!c_container || !btn) return;

            btn.style.color = favorites.includes(currentSymbol) ? 'var(--accent)' : 'var(--text)';

            c_container.innerHTML = "";
            m_container.innerHTML = "";

            favorites.forEach(fav => {
                const isCrypto = fav.includes("USDT");
                const div = document.createElement('div');
                div.innerHTML = fav;
                div.style.cssText = `padding: 8px 10px; background: rgba(255,255,255,0.03); border-radius: 4px; cursor: pointer; transition: 0.2s; color: #EAECEF; font-weight: 500;`;
                div.onmouseover = () => div.style.background = 'rgba(255,255,255,0.1)';
                div.onmouseout = () => div.style.background = 'rgba(255,255,255,0.03)';

                div.onclick = () => {
                    const nextMarket = isCrypto ? 'crypto' : 'moex';
                    document.getElementById('market-select').value = nextMarket;
                    currentSymbol = fav;
                    if (currentMarket !== nextMarket) changeMarket(nextMarket);
                    else { document.getElementById('symbol-select').value = fav; changeSymbol(fav); }
                    toggleWatchlistModal();
                };

                if (isCrypto) c_container.appendChild(div);
                else m_container.appendChild(div);
            });
        }

        const domElement = document.getElementById('tvchart');
        const layout = {
            plot_bgcolor: 'transparent', paper_bgcolor: 'transparent',
            margin: {t: 10, l: 50, r: 20, b: 40},
            xaxis: { showgrid: false, color: '#848E9C', type: 'category', nticks: 15, tickangle: -45 }, 
            yaxis: { showgrid: true, gridcolor: '#2B3139', color: '#848E9C', fixedrange: false },
            dragmode: 'pan', hovermode: 'x unified', shapes: []
        };

        async function loadHistory(symbol) {
            document.getElementById('active-symbol').innerText = symbol;
            const response = await fetch(`/api/history/${symbol}?t=${Date.now()}`);
            const result = await response.json();

            if (result.status === "ok") {
                const fiatSign = symbol.includes("USDT") ? "$" : "₽";
                const currentPrice = result.data.close[result.data.close.length - 1];

                const traceMain = {
                    x: result.data.time, close: result.data.close, high: result.data.high, low: result.data.low, open: result.data.open,
                    type: 'candlestick', name: symbol,
                    increasing: {line: {color: '#0ECB81'}}, decreasing: {line: {color: '#F6465D'}}
                };

                const traceBBHigh = {
                    x: result.data.time, y: result.data.bb_high, type: 'scatter', mode: 'lines',
                    line: {color: 'rgba(255, 255, 255, 0.2)', width: 1, dash: 'dot'}, hoverinfo: 'skip', name: 'BB High',
                    connectgaps: true
                };

                const traceBBLow = {
                    x: result.data.time, y: result.data.bb_low, type: 'scatter', mode: 'lines',
                    line: {color: 'rgba(255, 255, 255, 0.2)', width: 1, dash: 'dot'}, fill: 'tonexty', fillcolor: 'rgba(255,255,255,0.03)', hoverinfo: 'skip', name: 'BB Low',
                    connectgaps: true
                };

                layout.shapes = [];
                layout.shapes.push({ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: result.data.poc, y1: result.data.poc, line: {color: 'rgba(243, 186, 47, 0.4)', width: 2, dash: 'solid'} });
                result.data.levels.forEach(lvl => {
                    layout.shapes.push({ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: lvl.price, y1: lvl.price, line: {color: lvl.type === 'support' ? 'rgba(14, 203, 129, 0.3)' : 'rgba(246, 70, 93, 0.3)', width: 1, dash: 'dot'} });
                });

                layout.xaxis.autorange = true;
                layout.yaxis.autorange = true;

                Plotly.react(domElement, [traceBBHigh, traceBBLow, traceMain], layout, {responsive: true, displayModeBar: true, scrollZoom: true});

                document.getElementById('active-price').innerText = fiatSign + currentPrice.toFixed(2);
                document.getElementById('conn-status').innerText = '🟢 Ядро подключено (Live)';

                document.getElementById('xray-poc').innerText = fiatSign + result.data.poc.toFixed(2);
                document.getElementById('xray-rsi').innerText = result.data.rsi;
                const rsiEl = document.getElementById('xray-rsi-verdict');
                rsiEl.innerText = result.data.rsi < 35 ? "🟢 ПОКУПКА" : result.data.rsi > 65 ? "🔴 ПЕРЕГРЕВ" : "⚪ НЕЙТРАЛЬНО";

                const trendEl = document.getElementById('xray-sma');
                trendEl.innerText = currentPrice > result.data.sma ? "📈 UPTREND" : "📉 DOWNTREND";
                trendEl.style.color = currentPrice > result.data.sma ? "#0ECB81" : "#F6465D";
            }
        }

        async function loadLogs() {
            try {
                const res = await fetch('/api/logs');
                const result = await res.json();
                if (result.status === "ok") {
                    let htmlMini = "";
                    let htmlFull = "";

                    result.data.forEach(log => {
                        const cssClass = log.action.includes('BUY') ? 'buy' : log.action.includes('SELL') ? 'sell' : '';
                        const color = cssClass === 'buy' ? '#0ECB81' : cssClass === 'sell' ? '#F6465D' : '#848E9C';

                        const slTpHtml = log.sl > 0 ? `<div style="margin-top:5px; padding: 4px; border-radius: 4px; background: rgba(0,0,0,0.3); font-family: monospace;">🎯 TP: <span style="color:#0ECB81">${log.tp}</span> | 🛑 SL: <span style="color:#F6465D">${log.sl}</span></div>` : '';

                        htmlMini += `<div class="log-card ${cssClass}">
                            <div style="color:#848E9C;font-size:0.75rem;">${log.time} | ${log.symbol}</div>
                            <div style="font-weight:bold; color:${color}">${log.action} (${log.conf}%)</div>
                            ${slTpHtml}
                            <div style="font-size:0.75rem;color:#aaa;margin-top:4px;">${log.reason}</div>
                        </div>`;

                        htmlFull += `<div class="log-card ${cssClass}" style="margin-bottom: 12px; padding: 15px;">
                            <div style="color:#848E9C;font-size:0.85rem;">${log.time} | ${log.symbol}</div>
                            <div style="font-weight:bold; font-size:1.1rem; margin-bottom: 8px; color:${color}">${log.action} (Уверенность: ${log.conf}%)</div>
                            ${slTpHtml}
                            <div style="font-size:0.9rem; color:#EAECEF; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; border-left: 2px solid #555; margin-top: 8px;">
                                ${log.state}
                            </div>
                            <div style="font-size:0.9rem;color:var(--accent);margin-top:8px;">💡 Вывод: ${log.reason}</div>
                        </div>`;
                    });

                    document.getElementById('ai-logs-mini').innerHTML = htmlMini;
                    document.getElementById('ai-logs-full').innerHTML = htmlFull;
                }
            } catch (e) {}
        }

        async function loadPortfolio() {
            const response = await fetch(`/api/portfolio`);
            const result = await response.json();
            if (result.status === "ok") {
                result.fiat.forEach(f => { 
                    if(f.symbol === 'USDT') document.getElementById('bal-usdt').innerText = '$' + f.amount.toFixed(2);
                    if(f.symbol === 'RUB') document.getElementById('bal-rub').innerText = f.amount.toFixed(2) + ' ₽';
                });

                let cAssets = "<tr><th>Токен</th><th>Объем</th><th>Вход</th><th>PnL</th></tr>";
                let mAssets = "<tr><th>Акция</th><th>Объем</th><th>Вход</th><th>PnL</th></tr>";

                result.assets.forEach(a => { 
                    const pnlColor = a.pnl >= 0 ? '#0ECB81' : '#F6465D';
                    const pnlSign = a.pnl >= 0 ? '+' : '';
                    const pnlText = `<span style="color:${pnlColor}; font-weight:bold;">${pnlSign}${a.pnl} (${pnlSign}${a.pnl_pct}%)</span>`;

                    if(a.symbol.includes('USDT')) {
                        cAssets += `<tr><td style="color:#F3BA2F;">${a.symbol}</td><td>${a.amount.toFixed(4)}</td><td>$${a.entry.toFixed(2)}</td><td>${pnlText}</td></tr>`;
                    } else {
                        mAssets += `<tr><td style="color:#0ECB81;">${a.symbol}</td><td>${a.amount.toFixed(0)}</td><td>${a.entry.toFixed(2)} ₽</td><td>${pnlText}</td></tr>`;
                    }
                });

                document.getElementById('crypto-assets').innerHTML = cAssets;
                document.getElementById('moex-assets').innerHTML = mAssets;

                let cHist = "<tr><th>Время</th><th>Сигнал</th><th>Цена</th><th>Объем</th><th>Всего</th></tr>";
                let mHist = "<tr><th>Время</th><th>Сигнал</th><th>Цена</th><th>Объем</th><th>Всего</th></tr>";

                result.history.forEach(h => { 
                    const color = h.action.includes("BUY") ? "var(--green)" : "var(--red)";
                    const fiatSign = h.symbol.includes("USDT") ? "$" : "₽";

                    const row = `<tr>
                        <td style="color:#848E9C">${h.timestamp.split(' ')[1]}</td>
                        <td><strong style="color:${color}">${h.action}</strong><br><span style="font-size:0.75rem; color:#848E9C">${h.symbol}</span></td>
                        <td style="font-family:monospace">${fiatSign}${h.price.toFixed(2)}</td>
                        <td style="color:#fff; font-family:monospace">${h.amount.toFixed(4)}</td>
                        <td style="font-weight:bold; font-family:monospace">${fiatSign}${h.total_value.toFixed(2)}</td>
                    </tr>`;

                    if(h.symbol.includes('USDT')) cHist += row; else mHist += row;
                });
                document.getElementById('crypto-history').innerHTML = cHist;
                document.getElementById('moex-history').innerHTML = mHist;
            }
        }

        window.changeSymbol = function(newSymbol) {
            currentSymbol = newSymbol;
            document.getElementById('active-price').innerText = "Загрузка...";
            loadHistory(currentSymbol);
        };

        loadSettingsUI();
        changeMarket('crypto').then(() => {
            changeSymbol('BTCUSDT');
        });
        loadPortfolio();
        setInterval(loadPortfolio, 5000);
        loadLogs();
        setInterval(loadLogs, 5000);

        const ws = new WebSocket("ws://" + window.location.host + "/ws");
        ws.onmessage = function(event) {
            const msg = JSON.parse(event.data);
            if (msg.event === "TRADE_SIGNAL") {
                const data = msg.data;
                const cssClass = data.action.includes('BUY') ? 'buy' : data.action.includes('SELL') ? 'sell' : '';
                const color = cssClass === 'buy' ? '#0ECB81' : cssClass === 'sell' ? '#F6465D' : '#fff';

                const slTpHtml = data.sl > 0 ? `<div style="margin-top:4px; padding: 4px; background: rgba(0,0,0,0.3); border-radius: 4px; font-family: monospace; font-size: 0.8rem;">🎯 TP: <span style="color:#0ECB81">${data.tp}</span> | 🛑 SL: <span style="color:#F6465D">${data.sl}</span></div>` : '';

                const html = `<div class="log-card ${cssClass}">
                                  <div style="color:#848E9C;font-size:0.75rem;">${new Date().toLocaleTimeString()} | ${data.symbol}</div>
                                  <div style="font-weight:bold; color:${color}">${data.action}</div>
                                  ${slTpHtml}
                                  <div style="font-size:0.75rem;color:#aaa;margin-top:4px;">Логика: ${data.reason || "AI Signal"}</div>
                              </div>`;

                const miniBox = document.getElementById('ai-logs-mini');
                const fullBox = document.getElementById('ai-logs-full');
                if(miniBox) { miniBox.insertAdjacentHTML('afterbegin', html); if(miniBox.children.length > 10) miniBox.removeChild(miniBox.lastChild); }
                if(fullBox) { fullBox.insertAdjacentHTML('afterbegin', html); if(fullBox.children.length > 50) fullBox.removeChild(fullBox.lastChild); }

                if (data.sl > 0 && data.symbol === currentSymbol && layout.shapes) {
                    layout.shapes = layout.shapes.filter(s => s.name !== 'sltp');
                    layout.shapes.push({ name: 'sltp', type: 'line', x0: 0, x1: 1, xref: 'paper', y0: data.sl, y1: data.sl, line: {color: '#F6465D', width: 2, dash: 'dash'} });
                    layout.shapes.push({ name: 'sltp', type: 'line', x0: 0, x1: 1, xref: 'paper', y0: data.tp, y1: data.tp, line: {color: '#0ECB81', width: 2, dash: 'dash'} });
                    Plotly.relayout(domElement, { shapes: layout.shapes });
                }
            }
        };
    </script>
</body>
</html>
"""


@app.get("/")
async def get_dashboard(): return HTMLResponse(HTML_CONTENT)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = asyncio.Queue()

    async def on_signal(payload):
        await queue.put({"event": "TRADE_SIGNAL", "data": payload})

    system_bus.subscribe("TRADE_SIGNAL", on_signal)
    try:
        while True: await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
