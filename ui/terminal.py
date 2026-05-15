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

# Инициализация с открытым боковым меню
st.set_page_config(page_title="T-Alpha Pro Terminal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    header {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; font-size: 16px; font-weight: 600; color: #848E9C; }
    .stTabs [aria-selected="true"] { color: #F3BA2F !important; border-bottom: 2px solid #F3BA2F !important; }
    .xray-panel { background: linear-gradient(180deg, #161A25 0%, #0B0E14 100%); border: 1px solid #2B3139; border-radius: 4px; padding: 15px; }
    .stMetric { background-color: #161A25; border: 1px solid #2B3139; padding: 10px; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# --- УПРАВЛЕНИЕ ИИ ---
st.sidebar.title("⚙️ Настройки T-Alpha")
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".ai_config.json")


def load_cfg():
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except:
        return {"risk_profile": "Medium"}


config = load_cfg()
risk_idx = 0 if config.get("risk_profile") == "Low" else 1
selected_risk = st.sidebar.radio("Профиль Риска:", ["🟢 Низкий (Голубые фишки)", "🟡 Средний (Свинг-трейдинг)"],
                                 index=risk_idx)

if ("Low" if "🟢" in selected_risk else "Medium") != config.get("risk_profile"):
    with open(config_path, "w") as f:
        json.dump({"risk_profile": "Low" if "🟢" in selected_risk else "Medium"}, f)
    st.sidebar.success("Настройки применены!")


# --- ВИДЖЕТ ГРАФИКА ---
def render_tradingview_widget(symbol, is_crypto, tf_display):
    tv_symbol = f"BYBIT:{symbol}" if is_crypto else f"MOEX:{symbol}"
    tv_tf_map = {"15 Минут": "15", "1 Час": "60", "1 День": "D"}
    interval = tv_tf_map.get(tf_display, "15")
    url = f"https://s.tradingview.com/widgetembed/?symbol={tv_symbol}&interval={interval}&theme=dark&locale=ru"
    components.html(f'<iframe src="{url}" width="100%" height="600" frameborder="0" allowfullscreen></iframe>',
                    height=605)


@st.cache_data(ttl=60)
def fetch_live_data(symbol, m_type):
    df = pd.DataFrame()
    try:
        if m_type == "crypto":
            client = HTTP(testnet=False)
            res = client.get_kline(category="linear", symbol=symbol, interval='15', limit=100)
            if res['retCode'] == 0:
                df = pd.DataFrame(res['result']['list'],
                                  columns=['ts', 'open', 'high', 'low', 'close', 'vol', 'turnover'])
                df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')
        else:
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?interval=10"
            res = requests.get(url).json()
            df = pd.DataFrame(res['candles']['data'], columns=res['candles']['columns'])
            df = df.rename(columns={'end': 'ts'})
            df['ts'] = pd.to_datetime(df['ts'])

        if not df.empty:
            for c in ['open', 'high', 'low', 'close', 'vol']: df[c] = df[c].astype(float)
            df = df.sort_values('ts')
    except:
        pass
    return df


def get_balances(fiat, asset):
    conn = get_connection()
    f_bal = pd.read_sql_query(f"SELECT amount FROM portfolio WHERE symbol='{fiat}'", conn)
    a_bal = pd.read_sql_query(f"SELECT amount FROM portfolio WHERE symbol='{asset}'", conn)
    conn.close()
    return f_bal.iloc[0]['amount'] if not f_bal.empty else 0.0, a_bal.iloc[0]['amount'] if not a_bal.empty else 0.0


# --- ВКЛАДКИ ---
tab_term, tab_screen, tab_stats = st.tabs(["📊 ТЕРМИНАЛ", "🧠 AI-СКРИНЕР", "📈 ПОРТФЕЛЬ И СТАТИСТИКА"])

with tab_term:
    m_mode = st.radio("Рынок", ["Bybit (Крипта)", "MOEX (Акции)"], horizontal=True, label_visibility="collapsed")
    is_crypto = "Bybit" in m_mode
    assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] if is_crypto else ["SBER", "LKOH", "GAZP", "YDEX"]
    fiat, sign = ("USDT", "$") if is_crypto else ("RUB", "₽")

    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
    with c1:
        symbol = st.selectbox("Актив", assets, label_visibility="collapsed")
    with c2:
        tf = st.selectbox("ТФ", ["15 Минут", "1 Час", "1 День"], label_visibility="collapsed")

    df = fetch_live_data(symbol, "crypto" if is_crypto else "stocks")
    f_bal, a_bal = get_balances(fiat, symbol)

    if not df.empty:
        price = df['close'].iloc[-1]
        with c3: st.metric("Цена", f"{sign}{price:,.2f}")
        with c4: st.metric(f"Баланс {fiat}", f"{sign}{f_bal:,.2f}")
        with c5: st.metric(f"В наличии", f"{a_bal:.4f}")

    st.markdown("---")
    main, side = st.columns([3, 1])
    with main:
        render_tradingview_widget(symbol, is_crypto, tf)
    with side:
        st.markdown("<div class='xray-panel'><h5>🔍 X-RAY АНАЛИЗ</h5>", unsafe_allow_html=True)
        if not df.empty and len(df) > 14:
            rsi = ta.momentum.RSIIndicator(df['close']).rsi().iloc[-1]
            st.write(f"**RSI (14):** {rsi:.2f}")
            if rsi < 30:
                st.success("ЗОНА ПОКУПКИ")
            elif rsi > 70:
                st.error("ЗОНА ПРОДАЖИ")
            else:
                st.info("НЕЙТРАЛЬНО")
        st.markdown("</div>", unsafe_allow_html=True)

with tab_screen:
    st.header("🎯 Актуальные сигналы системы")
    conn = get_connection()
    df_sig = pd.read_sql_query(
        "SELECT timestamp, market_state, ai_decision FROM experience_replay ORDER BY id DESC LIMIT 15", conn)
    conn.close()
    if not df_sig.empty:
        for _, row in df_sig.iterrows():
            with st.expander(f"🕒 {row['timestamp']} | {row['market_state'][:50]}..."):
                st.json(json.loads(row['ai_decision']))
    else:
        st.info("Сканер в режиме ожидания...")

with tab_stats:
    st.header("📊 Учет и эффективность")
    conn = get_connection()
    df_h = pd.read_sql_query("SELECT * FROM trade_history ORDER BY id DESC", conn)
    df_p = pd.read_sql_query("SELECT symbol, amount FROM portfolio WHERE amount > 0", conn)
    conn.close()

    m1, m2 = st.columns(2)
    m1.metric("Всего операций", len(df_h))
    m2.metric("Активов в портфеле", len(df_p))

    st.subheader("📦 Текущий состав портфеля")
    st.table(df_p)
    st.subheader("📝 Журнал всех сделок")
    st.dataframe(df_h, use_container_width=True)