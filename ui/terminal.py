import streamlit as st
import pandas as pd
import json
import os
import requests
import ta
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection

# Инициализация интерфейса T-Alpha Pro
st.set_page_config(page_title="T-Alpha Pro Terminal", layout="wide")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".ai_config.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"risk_profile": "Medium"}


def save_config(risk):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"risk_profile": risk}, f, ensure_ascii=False)


# Стилизация под профессиональный темный терминал
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 1.5rem; padding-right: 1.5rem; max-width: 100%; }
    .stMetric { background-color: #161A25; border: 1px solid #2B3139; padding: 12px; border-radius: 6px; }
    .xray-panel { background: #161A25; border: 1px solid #F3BA2F; padding: 18px; border-radius: 8px; min-height: 515px; }
    header {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 48px; border-radius: 4px 4px 0 0; padding: 0 24px;
        background-color: #161A25; color: #848E9C; font-weight: 600;
    }
    .stTabs [aria-selected="true"] { background-color: #2B3139 !important; color: #F3BA2F !important; border-bottom: 2px solid #F3BA2F !important; }
</style>
""", unsafe_allow_html=True)


# --- ИНТЕГРАЦИЯ ВСЕХ ДОСТУПНЫХ АКТИВОВ С БИРЖ ---
@st.cache_data(ttl=3600)
def get_crypto_assets_list():
    try:
        from pybit.unified_trading import HTTP
        client = HTTP()
        res = client.get_instruments_info(category="linear")
        return sorted([x['symbol'] for x in res['result']['list'] if
                       x['quoteCoin'] == 'USDT' and not x['symbol'].startswith('1000')])
    except:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@st.cache_data(ttl=3600)
def get_moex_assets_list():
    try:
        url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=securities"
        res = requests.get(url, timeout=5).json()
        return sorted([x[0] for x in res['securities']['data']])
    except:
        return ["SBER", "LKOH", "GAZP", "YDEX", "TCSG"]


# --- СБОР ДАННЫХ ДЛЯ X-RAY ---
@st.cache_data(ttl=15)
def fetch_hub_candles(symbol, market_mode):
    try:
        if market_mode == "crypto":
            from pybit.unified_trading import HTTP
            client = HTTP(testnet=False)
            res = client.get_kline(category="linear", symbol=symbol, interval="15", limit=150)
            if res['retCode'] == 0:
                df = pd.DataFrame(res['result']['list'], columns=['ts', 'o', 'h', 'l', 'c', 'v', 't'])
                df = df.iloc[::-1]
                for col in ['o', 'h', 'l', 'c', 'v']: df[col] = df[col].astype(float)
                return df
        else:
            # Используем дневные свечи (интервал 24) для стабильного расчета SMA200 и RSI фонда
            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?interval=24&limit=150"
            res = requests.get(url, timeout=5).json()
            if 'candles' in res and res['candles']['data']:
                df = pd.DataFrame(res['candles']['data'], columns=res['candles']['columns'])
                df = df.rename(
                    columns={'begin': 'ts', 'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
                for col in ['o', 'h', 'l', 'c', 'v']: df[col] = df[col].astype(float)
                return df
    except:
        pass
    return pd.DataFrame()


def load_hub_finances(market_mode):
    conn = get_connection()
    if market_mode == "crypto":
        df_history = pd.read_sql_query(
            "SELECT timestamp, symbol, action, price, amount, total_value, reason FROM trade_history WHERE symbol LIKE '%USDT%' OR symbol IN ('BTCUSDT', 'ETHUSDT', 'SOLUSDT') ORDER BY id DESC",
            conn)
        df_portfolio = pd.read_sql_query(
            "SELECT symbol, amount, average_entry_price FROM portfolio WHERE amount > 0 AND symbol NOT IN ('RUB')",
            conn)
    else:
        df_history = pd.read_sql_query(
            "SELECT timestamp, symbol, action, price, amount, total_value, reason FROM trade_history WHERE symbol NOT LIKE '%USDT%' AND symbol NOT IN ('BTCUSDT', 'ETHUSDT', 'SOLUSDT') ORDER BY id DESC",
            conn)
        df_portfolio = pd.read_sql_query(
            "SELECT symbol, amount, average_entry_price FROM portfolio WHERE amount > 0 AND symbol NOT IN ('USDT')",
            conn)
    conn.close()
    return df_history, df_portfolio


# ЗАГРУЗКА ДАННЫХ
conf_data = load_config()
all_crypto = get_crypto_assets_list()
all_moex = get_moex_assets_list()

# НАВИГАЦИЯ ХАБОВ
hub_crypto, hub_moex = st.tabs(["🪙 КРИПТО-ХАБ (BYBIT)", "🏛️ ФОНДОВЫЙ-ХАБ (MOEX)"])

# ==============================================================================
# 🪙 КРИПТО-ХАБ
# ==============================================================================
with hub_crypto:
    term_c, screen_c, stats_c = st.tabs(["📊 ТЕРМИНАЛ", "🧠 AI-СКРИНЕР", "📈 ПОРТФЕЛЬ И СТАТИСТИКА"])

    with term_c:
        col_chart, col_xray = st.columns([3.2, 0.8])
        with col_chart:
            c1, c2 = st.columns([2, 1])
            crypto_symbol = c1.selectbox("Выберите инструмент", all_crypto,
                                         index=all_crypto.index("BTCUSDT") if "BTCUSDT" in all_crypto else 0,
                                         key="c_sym")
            crypto_tf = c2.selectbox("Таймфрейм графика", ["15 Минут", "1 Час", "1 День"], key="c_tf")

            tf_tv_map = {"15 Минут": "15", "1 Час": "60", "1 День": "D"}

            # Оптимизированный контейнер графика (на всю ширину колонки)
            st.components.v1.iframe(
                src=f"https://s.tradingview.com/widgetembed/?symbol=BYBIT:{crypto_symbol}&interval={tf_tv_map[crypto_tf]}&theme=dark&locale=ru",
                height=520,
                scrolling=False
            )

        with col_xray:
            st.markdown("<div class='xray-panel'>", unsafe_allow_html=True)
            st.markdown(f"#### 🔍 X-RAY АНАЛИЗ\n**{crypto_symbol}**")
            candles_df = fetch_hub_candles(crypto_symbol, "crypto")

            if not candles_df.empty and len(candles_df) >= 15:
                live_price = candles_df['c'].iloc[-1]
                rsi_value = ta.momentum.RSIIndicator(candles_df['c'], window=14).rsi().iloc[-1]

                st.metric("Текущая цена", f"${live_price:,.2f}")
                st.metric("Мгновенный RSI", f"{rsi_value:.2f}")

                if rsi_value < 35:
                    st.success("Вердикт: ЗОНА ПОКУПКИ 🟢")
                elif rsi_value > 65:
                    st.error("Вердикт: ПЕРЕГРЕВ 🔴")
                else:
                    st.info("Вердикт: НЕЙТРАЛЬНО ⚪")
            else:
                st.warning("Ожидание стабильного потока данных...")
            st.markdown("</div>", unsafe_allow_html=True)

    with screen_c:
        st.subheader("🛡️ Управление Рисками ИИ (Крипта)")
        selected_risk = st.radio(
            "Профиль безопасности фонового сканера:",
            ["🟢 Низкий Риск (Только BTC/ETH + Фильтр тренда SMA 200)", "🟡 Средний Риск (Полный спектр волатильности)"],
            index=0 if conf_data.get("risk_profile") == "Low" else 1,
            key="risk_radio_c"
        )
        new_risk_profile = "Low" if "🟢" in selected_risk else "Medium"
        if new_risk_profile != conf_data.get("risk_profile"):
            save_config(new_risk_profile)
            st.success("Сканер успешно перенастроен!")

        st.markdown("---")
        st.subheader("📡 Лента активности ИИ-Автопилота")
        conn = get_connection()
        crypto_signals = pd.read_sql_query(
            "SELECT timestamp, market_state, ai_decision FROM experience_replay WHERE market_state LIKE '%[CRYPTO]%' ORDER BY id DESC LIMIT 15",
            conn)
        conn.close()

        if not crypto_signals.empty:
            for idx, row in crypto_signals.iterrows():
                try:
                    decision_json = json.loads(row['ai_decision'])
                    action = decision_json.get("action", "HOLD")
                    reason = decision_json.get("reason", "Анализ завершен")
                    icon = "🟢" if "BUY" in action else "🔴" if "SELL" in action else "⚪"
                    with st.expander(
                            f"{icon} {row['timestamp']} | {row['market_state'].split('Аномалия: ')[1].split('.')[0]} | Действие: {action}"):
                        st.write(f"**Обоснование ИИ:** {reason}")
                        st.json(decision_json)
                except:
                    pass
        else:
            st.info("Ожидание фоновых сигналов сканера...")

    with stats_c:
        h_df, p_df = load_hub_finances("crypto")

        free_usdt = p_df[p_df['symbol'] == 'USDT']['amount'].values[0] if not p_df[
            p_df['symbol'] == 'USDT'].empty else 0.0
        active_positions = p_df[p_df['symbol'] != 'USDT']

        crypto_buys = h_df[h_df['action'] == 'BUY']['total_value'].sum()
        crypto_sells = h_df[h_df['action'] == 'SELL']['total_value'].sum()
        crypto_profit = crypto_sells - crypto_buys if crypto_sells > 0 else 0.0

        m1, m2, m3 = st.columns(3)
        m1.metric("Свободный баланс", f"${free_usdt:,.2f}")
        m2.metric("Чистый Профит (Крипта)", f"${crypto_profit:,.2f}",
                  delta=f"{crypto_profit:+.2f}$" if crypto_profit != 0 else None)
        m3.metric("Активных позиций", len(active_positions))

        st.markdown("---")
        c_p, c_h = st.columns([1, 2])
        with c_p:
            st.markdown("#### 📦 Купленные токены")
            st.dataframe(active_positions, hide_index=True, width=400)
        with c_h:
            st.markdown("#### 📜 Журнал сделок Bybit")
            st.dataframe(h_df, hide_index=True, width=1000)

# ==============================================================================
# 🏛️ ФОНДОВЫЙ-ХАБ (MOEX)
# ==============================================================================
with hub_moex:
    term_m, screen_m, stats_m = st.tabs(["📊 ТЕРМИНАЛ", "🧠 AI-СКРИНЕР", "📈 ПОРТФЕЛЬ И СТАТИСТИКА"])

    with term_m:
        col_chart_m, col_xray_m = st.columns([3.2, 0.8])
        with col_chart_m:
            c1m, c2m = st.columns([2, 1])
            moex_symbol = c1m.selectbox("Выберите акцию", all_moex,
                                        index=all_moex.index("SBER") if "SBER" in all_moex else 0, key="m_sym")
            moex_tf = c2m.selectbox("Таймфрейм графика", ["15 Минут", "1 Час", "1 День"], key="m_tf")

            # Исправленный маппинг таймфреймов для Московской Биржи (убран ошибочный интервал 10)
            moex_tf_map = {"15 Минут": "15", "1 Час": "60", "1 День": "D"}

            # Исправленный вызов виджета TradingView для MOEX (Отказоустойчивый эмбед)
            st.components.v1.iframe(
                src=f"https://s.tradingview.com/widgetembed/?symbol=MOEX:{moex_symbol}&interval={moex_tf_map[moex_tf]}&theme=dark&locale=ru",
                height=520,
                scrolling=False
            )

        with col_xray_m:
            st.markdown("<div class='xray-panel'>", unsafe_allow_html=True)
            st.markdown(f"#### 🔍 X-RAY АНАЛИЗ\n**{moex_symbol}**")
            candles_df_m = fetch_hub_candles(moex_symbol, "stocks")

            if not candles_df_m.empty and len(candles_df_m) >= 15:
                live_price_m = candles_df_m['c'].iloc[-1]
                rsi_value_m = ta.momentum.RSIIndicator(candles_df_m['c'], window=14).rsi().iloc[-1]

                st.metric("Цена акции", f"{live_price_m:,.2f} ₽")
                st.metric("Мгновенный RSI", f"{rsi_value_m:.2f}")

                sma200 = candles_df_m['c'].mean() if len(candles_df_m) < 200 else \
                candles_df_m['c'].rolling(200).mean().iloc[-1]
                if live_price_m > sma200:
                    st.success("UPTREND 📈 (Выше SMA 200)")
                else:
                    st.error("DOWNTREND 📉 (Ниже SMA 200)")
            else:
                st.warning("Ожидание стабильного потока данных...")
            st.markdown("</div>", unsafe_allow_html=True)

    with screen_m:
        st.subheader("📡 Лента активности ИИ-Автопилота (Фонда)")
        conn = get_connection()
        moex_signals = pd.read_sql_query(
            "SELECT timestamp, market_state, ai_decision FROM experience_replay WHERE market_state LIKE '%[MOEX]%' ORDER BY id DESC LIMIT 15",
            conn)
        conn.close()

        if not moex_signals.empty:
            for idx, row in moex_signals.iterrows():
                try:
                    decision_json = json.loads(row['ai_decision'])
                    action = decision_json.get("action", "HOLD")
                    reason = decision_json.get("reason", "Анализ завершен")
                    icon = "🟢" if "BUY" in action else "🔴" if "SELL" in action else "⚪"
                    with st.expander(
                            f"{icon} {row['timestamp']} | {row['market_state'].split('Аномалия: ')[1].split('.')[0]} | Действие: {action}"):
                        st.write(f"**Обоснование ИИ:** {reason}")
                        st.json(decision_json)
                except:
                    pass
        else:
            st.info("Фондовый радар активен. Ночью и по выходным торги закрыты.")

    with stats_m:
        h_df_m, p_df_m = load_hub_finances("stocks")

        free_rub = p_df_m[p_df_m['symbol'] == 'RUB']['amount'].values[0] if not p_df_m[
            p_df_m['symbol'] == 'RUB'].empty else 0.0
        active_positions_m = p_df_m[(p_df_m['symbol'] != 'RUB') & (p_df_m['symbol'] != 'USDT')]

        moex_buys = h_df_m[h_df_m['action'] == 'BUY']['total_value'].sum()
        moex_sells = h_df_m[h_df_m['action'] == 'SELL']['total_value'].sum()
        moex_profit = moex_sells - moex_buys if moex_sells > 0 else 0.0

        m1m, m2m, m3m = st.columns(3)
        m1m.metric("Свободный баланс RUB", f"{free_rub:,.2f} ₽")
        m2m.metric("Чистый Профит (Фонда)", f"{moex_profit:,.2f} ₽",
                   delta=f"{moex_profit:+.2f}₽" if moex_profit != 0 else None)
        m3m.metric("Куплено видов акций", len(active_positions_m))

        st.markdown("---")
        c_p_m, c_h_m = st.columns([1, 2])
        with c_p_m:
            st.markdown("#### 📦 Купленные акции")
            st.dataframe(active_positions_m, hide_index=True, width=400)
        with c_h_m:
            st.markdown("#### 📜 Журнал сделок MOEX")
            st.dataframe(h_df_m, hide_index=True, width=1000)