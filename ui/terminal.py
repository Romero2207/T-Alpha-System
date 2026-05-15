import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit.components.v1 as components
import sys
import os
import json
import requests
import ta
from pybit.unified_trading import HTTP

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection

st.set_page_config(page_title="T-Alpha Pro Terminal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    header {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; font-size: 16px; font-weight: 600; color: #848E9C; }
    .stTabs [aria-selected="true"] { color: #F3BA2F !important; border-bottom: 2px solid #F3BA2F !important; }
    .trade-panel { background-color: #161A25; border: 1px solid #2B3139; border-radius: 4px; padding: 15px; }
    .xray-panel { background: linear-gradient(180deg, #161A25 0%, #0B0E14 100%); border: 1px solid #2B3139; border-radius: 4px; padding: 15px; }
    .log-card { background-color: #161A25; border-left: 3px solid #2B3139; padding: 10px; margin-bottom: 8px; font-family: monospace; font-size: 12px;}
    .stButton>button { width: 100%; }
</style>
""", unsafe_allow_html=True)

# --- ИСПРАВЛЕНИЕ 1: Скрытый файл конфига и безопасное сохранение ---
st.sidebar.title("⚙️ Настройки ИИ")
st.sidebar.markdown("Здесь вы можете изменить поведение сканера.")

config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".ai_config.json")

def load_config():
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"risk_profile": "Medium"}

def save_config():
    new_risk = "Low" if "🟢" in st.session_state.risk_selector else "Medium"
    conf = load_config()
    conf["risk_profile"] = new_risk
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(conf, f)

config = load_config()
risk_idx = 0 if config.get("risk_profile") == "Low" else 1

st.sidebar.radio(
    "Профиль Риска:",
    ["🟢 Низкий (Голубые фишки + Тренд)", "🟡 Средний (Топ-30 + Свинг)"],
    index=risk_idx,
    key="risk_selector",
    on_change=save_config
)
st.sidebar.markdown("---")


# --- ИСПРАВЛЕНИЕ 2: Жесткая высота для виджета TradingView ---
def render_tradingview_widget(symbol, is_crypto, tf_display):
    tv_symbol = f"BINANCE:{symbol}" if is_crypto else f"MOEX:{symbol}"
    tv_tf_map = {"1 Минута": "1", "5 Минут": "5", "15 Минут": "15", "1 Час": "60", "1 День": "D"}
    interval = tv_tf_map.get(tf_display, "15")

    html = f"""
    <div class="tradingview-widget-container" style="height:600px; width:100%;">
      <div id="tv_chart_{symbol}" style="height:600px; width:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": false,
        "width": "100%",
        "height": "600",
        "symbol": "{tv_symbol}",
        "interval": "{interval}",
        "timezone": "Europe/Moscow",
        "theme": "dark",
        "style": "1",
        "locale": "ru",
        "enable_publishing": false,
        "backgroundColor": "#0B0E14",
        "gridColor": "#1F242F",
        "hide_top_toolbar": false,
        "container_id": "tv_chart_{symbol}"
      }});
      </script>
    </div>
    """
    components.html(html, height=620)

@st.cache_data(ttl=60)
def fetch_live_chart(symbol, market_type, tf_crypto='15', tf_moex='10'):
    df = pd.DataFrame()
    try:
        if market_type == "crypto":
            client = HTTP(testnet=False)
            res = client.get_kline(category="linear", symbol=symbol, interval=tf_crypto, limit=200)
            if res['retCode'] == 0:
                klines = res['result']['list']
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
        else:
            from datetime import datetime, timedelta
            days_back = 30 if tf_moex in ['60', '24'] else 4
            start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?iss.meta=off&interval={tf_moex}&from={start_date}"
            res = requests.get(url, timeout=5).json()
            candles = res['candles']['data']
            cols = res['candles']['columns']
            df = pd.DataFrame(candles, columns=cols)
            df = df.rename(columns={'end': 'timestamp'})
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        if not df.empty:
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
            df = df.sort_values('timestamp')
    except Exception as e:
        pass
    return df

@st.cache_data(ttl=3600)
def get_all_crypto_symbols():
    try:
        client = HTTP()
        res = client.get_instruments_info(category="linear")
        return sorted([x['symbol'] for x in res['result']['list'] if x['quoteCoin'] == 'USDT' and not x['symbol'].startswith('1000')])
    except:
        return ["BTCUSDT", "ETHUSDT"]

@st.cache_data(ttl=3600)
def get_all_moex_symbols():
    try:
        url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=securities"
        res = requests.get(url, timeout=5).json()
        return sorted([x[0] for x in res['securities']['data']])
    except:
        return ["SBER", "GAZP"]

def load_user_portfolio(fiat_symbol, asset_symbol):
    conn = get_connection()
    f_df = pd.read_sql_query(f"SELECT amount FROM portfolio WHERE symbol='{fiat_symbol}'", conn)
    a_df = pd.read_sql_query(f"SELECT amount, average_entry_price FROM portfolio WHERE symbol='{asset_symbol}'", conn)
    conn.close()
    fiat_bal = f_df.iloc[0]['amount'] if not f_df.empty else 0.0
    asset_bal = a_df.iloc[0]['amount'] if not a_df.empty else 0.0
    avg_entry = a_df.iloc[0]['average_entry_price'] if not a_df.empty and 'average_entry_price' in a_df.columns else 0.0
    return fiat_bal, asset_bal, avg_entry

tab_terminal, tab_ai_screener, tab_stats = st.tabs(["📊 РУЧНОЙ ТЕРМИНАЛ", "🧠 AI-СКРИНЕР (АВТОПИЛОТ)", "📈 СТАТИСТИКА И ИСТОРИЯ"])

with tab_terminal:
    market_mode = st.radio("Рынок:", ["Криптовалюта (Bybit)", "Фондовый рынок (MOEX)"], horizontal=True, label_visibility="collapsed")
    is_crypto = "Bybit" in market_mode
    market_type = "crypto" if is_crypto else "stocks"
    assets = get_all_crypto_symbols() if is_crypto else get_all_moex_symbols()
    default_asset = "BTCUSDT" if is_crypto else "SBER"
    fiat = "USDT" if is_crypto else "RUB"
    fiat_sign = "$" if is_crypto else "₽"

    col_sel, col_tf, col_p, col_c, col_b, col_a = st.columns([1.5, 1, 1, 1, 1, 1])
    with col_sel:
        symbol = st.selectbox("Инструмент", assets, index=assets.index(default_asset) if default_asset in assets else 0, label_visibility="collapsed")
    with col_tf:
        tf_display = st.selectbox("Таймфрейм", ["1 Минута", "5 Минут", "15 Минут", "1 Час", "1 День"], index=2, label_visibility="collapsed")
        tf_map_crypto = {"1 Минута": "1", "5 Минут": "5", "15 Минут": "15", "1 Час": "60", "1 День": "D"}
        tf_map_moex = {"1 Минута": "1", "5 Минут": "10", "15 Минут": "10", "1 Час": "60", "1 День": "24"}
        c_tf, m_tf = tf_map_crypto[tf_display], tf_map_moex[tf_display]

    df_chart = fetch_live_chart(symbol, market_type, tf_crypto=c_tf, tf_moex=m_tf)
    fiat_bal, asset_bal, avg_entry = load_user_portfolio(fiat, symbol)

    current_price = df_chart['close'].iloc[-1] if not df_chart.empty else 0.0
    change_pct = ((current_price - df_chart['open'].iloc[0]) / df_chart['open'].iloc[0]) * 100 if not df_chart.empty else 0.0

    with col_p: st.metric("Цена", f"{fiat_sign}{current_price:,.2f}")
    with col_c: st.metric("Динамика", f"{change_pct:+.2f}%", delta_color="normal" if change_pct >= 0 else "inverse")
    with col_b: st.metric(f"Свободно ({fiat})", f"{fiat_sign}{fiat_bal:,.2f}")
    with col_a: st.metric(f"В позиции ({symbol})", f"{asset_bal:.4f}")

    st.markdown("<hr style='margin: 5px 0 10px 0; border-color: #2B3139;'>", unsafe_allow_html=True)

    main_col, side_col = st.columns([3, 1])

    with main_col:
        chart_type = st.radio("Режим графика:", ["Внутренний AI-График (Быстрый)", "TradingView Pro (Рисование)"], horizontal=True)

        if chart_type == "TradingView Pro (Рисование)":
            render_tradingview_widget(symbol, is_crypto, tf_display)
        else:
            if not df_chart.empty:
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
                fig.add_trace(go.Candlestick(x=df_chart['timestamp'], open=df_chart['open'], high=df_chart['high'], low=df_chart['low'], close=df_chart['close'], increasing_line_color='#0ECB81', decreasing_line_color='#F6465D', name='Цена'), row=1, col=1)
                colors = ['#0ECB81' if row['close'] >= row['open'] else '#F6465D' for idx, row in df_chart.iterrows()]
                fig.add_trace(go.Bar(x=df_chart['timestamp'], y=df_chart['volume'], marker_color=colors, name='Объем'), row=2, col=1)
                fig.update_layout(height=600, margin=dict(l=0, r=50, t=10, b=0), plot_bgcolor='#0B0E14', paper_bgcolor='#0B0E14', xaxis_rangeslider_visible=False, showlegend=False, dragmode='pan')
                fig.update_yaxes(showgrid=True, gridcolor='#1F242F', side="right", row=1)
                fig.update_yaxes(showgrid=False, showticklabels=False, row=2)
                st.plotly_chart(fig, config={'scrollZoom': True, 'displayModeBar': False})
            else:
                st.warning("Ожидание данных от API биржи...")

    with side_col:
        st.markdown("<div class='xray-panel'>", unsafe_allow_html=True)
        st.markdown("##### 🔍 РЕНТГЕН АКТИВА (LIVE)")

        if not df_chart.empty and len(df_chart) > 15:
            close_s, high_s, low_s = df_chart['close'], df_chart['high'], df_chart['low']
            rsi = ta.momentum.RSIIndicator(close_s, window=14).rsi().iloc[-1]
            macd = ta.trend.MACD(close_s).macd_diff().iloc[-1]
            atr = ta.volatility.AverageTrueRange(high=high_s, low=low_s, close=close_s, window=14).average_true_range().iloc[-1]

            rsi_color = "#0ECB81" if rsi < 35 else "#F6465D" if rsi > 65 else "#848E9C"
            macd_color = "#0ECB81" if macd > 0 else "#F6465D"

            st.markdown(f"**RSI (Перегрев):** <span style='color:{rsi_color}'>{rsi:.2f}</span>", unsafe_allow_html=True)
            st.markdown(f"**MACD (Тренд):** <span style='color:{macd_color}'>{macd:.4f}</span>", unsafe_allow_html=True)
            st.markdown(f"**ATR (Волатильность):** {fiat_sign}{atr:.2f}")

            prev, curr = df_chart.iloc[-2], df_chart.iloc[-1]
            is_bull = (prev['close'] < prev['open']) and (curr['close'] > curr['open']) and (curr['close'] >= prev['open']) and (curr['open'] <= prev['close'])
            is_bear = (prev['close'] > prev['open']) and (curr['close'] < curr['open']) and (curr['open'] >= prev['close']) and (curr['close'] <= prev['open'])

            pat_text = "Бычье поглощение 🟢" if is_bull else "Медвежье поглощение 🔴" if is_bear else "Нет формации ⚪"
            st.markdown(f"**Паттерн:** {pat_text}")

            st.markdown("<hr style='margin: 10px 0; border-color: #2B3139;'>", unsafe_allow_html=True)
            if rsi < 35 and macd > 0: st.success("Вердикт: ПОКУПКА")
            elif rsi > 65 and macd < 0: st.error("Вердикт: ПРОДАЖА")
            else: st.info("Вердикт: НЕЙТРАЛЬНО")
        else:
            st.write("Сбор данных...")
        st.markdown("</div>", unsafe_allow_html=True)

with tab_ai_screener:
    st.header("🌐 ГЛОБАЛЬНЫЙ СКАНЕР РЫНКА (АВТОПИЛОТ)")
    col_upd, _ = st.columns([1, 5])
    if col_upd.button("🔄 Обновить радар"): st.rerun()

    sub_crypto, sub_stocks = st.tabs(["🪙 РАДАР BYBIT (24/7)", "🏛️ РАДАР MOEX (Фонда)"])

    conn = get_connection()
    df_signals = pd.read_sql_query("SELECT timestamp, market_state, ai_decision FROM experience_replay WHERE market_state LIKE '%Аномалия:%' ORDER BY id DESC LIMIT 40", conn)
    conn.close()

    def render_signal_card(row, sym):
        try:
            dec = json.loads(row['ai_decision'])
            action, conf, reason, price, change = dec.get("action", "HOLD"), dec.get("confidence", 0), dec.get("reason", ""), dec.get("current_price", 0.0), dec.get("market_change", 0.0)
            icon = "🟢" if "BUY" in action and "Blocked" not in action else "🔴" if "SELL" in action and "Blocked" not in action else "⚪"
            with st.expander(f"{icon} {row['timestamp']} | {sym} | {action} ({conf}%) | Изменение: {change:+.2f}%"):
                st.write(f"**Обоснование ИИ:** {reason}")
                m1, m2, m3 = st.columns(3)
                m1.metric("Цена", f"{price:,.4f}")
                m2.metric("Take Profit", f"{dec.get('take_profit', 0.0):,.4f}")
                m3.metric("Stop Loss", f"{dec.get('stop_loss', 0.0):,.4f}")
        except: pass

    with sub_crypto:
        crypto_signals = df_signals[df_signals['market_state'].str.contains(r'\[CRYPTO\]')]
        if not crypto_signals.empty:
            for _, row in crypto_signals.iterrows(): render_signal_card(row, row['market_state'].split("Аномалия: ")[1].split(".")[0])
        else: st.info("Радар Bybit собирает данные...")

    with sub_stocks:
        stock_signals = df_signals[df_signals['market_state'].str.contains(r'\[MOEX\]')]
        if not stock_signals.empty:
            for _, row in stock_signals.iterrows(): render_signal_card(row, row['market_state'].split("Аномалия: ")[1].split(".")[0])
        else: st.info("Радар MOEX собирает данные...")

with tab_stats:
    st.header("👤 ПРОФИЛЬ ИНВЕСТОРА T-ALPHA")
    conn = get_connection()
    df_port = pd.read_sql_query("SELECT symbol, amount FROM portfolio WHERE amount > 0", conn)
    df_hist = pd.read_sql_query("SELECT timestamp, symbol, action, price, amount, total_value, reason FROM trade_history ORDER BY id DESC", conn)
    conn.close()

    total_turnover = df_hist['total_value'].sum() if not df_hist.empty else 0.0
    win_count, total_closed = 0, 0

    if not df_hist.empty:
        sells = df_hist[df_hist['action'].str.contains('SELL')]
        for _, sell in sells.iterrows():
            total_closed += 1
            if "Отк" in sell['reason'] or "🎯" in sell['reason']: win_count += 1

    winrate = (win_count / total_closed * 100) if total_closed > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Оборот", f"${total_turnover:,.2f}")
    m2.metric("Сделок закрыто", total_closed)
    m3.metric("Winrate", f"{winrate:.1f}%")
    m4.metric("Активных позиций", len(df_port))

    st.markdown("---")
    col_charts, col_info = st.columns([2, 1])

    with col_charts:
        st.subheader("📊 История операций")
        if not df_hist.empty: st.line_chart(df_hist.set_index('timestamp')['total_value'])
        else: st.info("Здесь появится график после первых сделок.")

    with col_info:
        st.subheader("📦 Ваши активы")
        if not df_port.empty:
            for _, asset in df_port.iterrows():
                if asset['symbol'] not in ['USDT', 'RUB']: st.write(f"**{asset['symbol']}**: {asset['amount']:.4f} шт.")
        else: st.write("Портфель пуст")

    st.subheader("📜 Журнал")
    st.dataframe(df_hist, width='stretch', hide_index=True)