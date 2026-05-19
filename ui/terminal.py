import streamlit as st
import pandas as pd
import json
import os
import requests
import ta
import sys
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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


# Стилизация под премиальный темный терминал
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 1.5rem; padding-right: 1.5rem; max-width: 100%; }
    .stMetric { background-color: #161A25; border: 1px solid #2B3139; padding: 12px; border-radius: 6px; }
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


# --- ДИНАМИЧЕСКИЙ СБОР ДАННЫХ ---
@st.cache_data(ttl=15)
def fetch_hub_candles(symbol, market_mode, tf_display="15 Минут"):
    try:
        if market_mode == "crypto":
            tf_map = {"15 Минут": "15", "1 Час": "60", "1 День": "D"}
            interval = tf_map.get(tf_display, "15")

            from pybit.unified_trading import HTTP
            client = HTTP(testnet=False)
            res = client.get_kline(category="linear", symbol=symbol, interval=interval, limit=150)
            if res['retCode'] == 0:
                df = pd.DataFrame(res['result']['list'], columns=['ts', 'o', 'h', 'l', 'c', 'v', 't'])
                df = df.iloc[::-1]
                for col in ['o', 'h', 'l', 'c', 'v']: df[col] = df[col].astype(float)
                df['ts'] = pd.to_datetime(pd.to_numeric(df['ts']), unit='ms')
                return df
        else:
            tf_map = {"15 Минут": "10", "1 Час": "60", "1 День": "24"}
            interval = tf_map.get(tf_display, "24")

            url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?interval={interval}&limit=150"
            res = requests.get(url, timeout=5).json()
            if 'candles' in res and res['candles']['data']:
                df = pd.DataFrame(res['candles']['data'], columns=res['candles']['columns'])
                df = df.rename(
                    columns={'begin': 'ts', 'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c', 'volume': 'v'})
                for col in ['o', 'h', 'l', 'c', 'v']: df[col] = df[col].astype(float)
                df['ts'] = pd.to_datetime(df['ts'])
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


# --- НАТИВНЫЙ РЕНДЕР ГРАФИКА: ПРОФИЛЬ ОБЪЕМА И АВТО-ТА ---
def render_native_chart(df, symbol):
    if df.empty:
        st.warning("Ожидание данных для отрисовки графика...")
        return

    # Убираем дыры во времени (Категориальная ось X)
    time_labels = df['ts'].dt.strftime('%d.%m %H:%M') if 'Минут' in st.session_state.get('c_tf',
                                                                                         '15 Минут') or 'Час' in st.session_state.get(
        'c_tf', '') else df['ts'].dt.strftime('%Y-%m-%d')

    # --- 1. АЛГОРИТМ ПРОФИЛЯ ОБЪЕМА (Volume Profile) ---
    min_p, max_p = df['l'].min(), df['h'].max()
    # Делим весь ценовой диапазон на 40 уровней
    bins = np.linspace(min_p, max_p, 40)
    df['typ_price'] = (df['h'] + df['l'] + df['c']) / 3
    df['bin'] = pd.cut(df['typ_price'], bins=bins)

    # Считаем сумму заявок (объема) на каждом уровне цены
    vol_profile = df.groupby('bin', observed=False)['v'].sum().reset_index()
    vol_profile['mid'] = vol_profile['bin'].apply(lambda x: x.mid)

    # Находим POC (Point of Control) - самый сильный уровень на графике
    poc_idx = vol_profile['v'].idxmax()
    poc_price = vol_profile.loc[poc_idx, 'mid']

    # Ищем другие крупные скопления ликвидности (Поддержки/Сопротивления)
    mean_vol = vol_profile['v'].mean()
    high_vol_nodes = vol_profile[vol_profile['v'] > mean_vol * 1.5]

    # --- СОЗДАНИЕ ДВОЙНОГО ХОЛСТА (Свечи + Гистограмма справа) ---
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, column_widths=[0.85, 0.15], horizontal_spacing=0.01)

    # Левая часть: Свечи
    fig.add_trace(go.Candlestick(
        x=time_labels, open=df['o'], high=df['h'], low=df['l'], close=df['c'],
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
        name=symbol, showlegend=False
    ), row=1, col=1)

    # Правая часть: Горизонтальные объемы (заявки)
    fig.add_trace(go.Bar(
        x=vol_profile['v'], y=vol_profile['mid'], orientation='h',
        marker_color='rgba(132, 142, 156, 0.4)',
        name='Объем заявок', showlegend=False, hoverinfo='skip'
    ), row=1, col=2)

    # --- 2. БОТ РИСУЕТ ТЕХ АНАЛИЗ ---
    current_price = df['c'].iloc[-1]

    # Отрисовка линии POC
    fig.add_hline(y=poc_price, line_dash="solid", line_color="#F3BA2F", line_width=2,
                  annotation_text="POC (Главная база)", annotation_position="top left",
                  annotation_font_color="#F3BA2F", row=1, col=1)

    # Отрисовка умных зон Поддержки и Сопротивления по объемам
    for _, row in high_vol_nodes.iterrows():
        price_lvl = row['mid']
        # Фильтруем линии, чтобы они не слипались с POC
        if abs(price_lvl - poc_price) > (max_p - min_p) * 0.04:
            color = "#ef5350" if price_lvl > current_price else "#26a69a"
            text = "Сопротивление" if price_lvl > current_price else "Поддержка"
            fig.add_hline(y=price_lvl, line_dash="dash",
                          line_color=f"rgba({'239,83,80' if color == '#ef5350' else '38,166,154'}, 0.5)",
                          annotation_text=text, annotation_position="top left", annotation_font_color=color,
                          annotation_font_size=10,
                          row=1, col=1)

    # Отрисовка Вектора Тренда (Бот проводит Линейную Регрессию)
    x_numeric = np.arange(len(df))
    z = np.polyfit(x_numeric, df['c'], 1)
    p = np.poly1d(z)

    fig.add_trace(go.Scatter(
        x=time_labels, y=p(x_numeric), mode='lines',
        line=dict(color='rgba(255, 255, 255, 0.5)', width=1.5, dash='dot'),
        name='Вектор тренда', showlegend=False
    ), row=1, col=1)

    # Настройки интерфейса графика
    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=10, b=0),
        height=540,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        dragmode='pan',  # Двигаем левой кнопкой мыши
        hovermode="x unified",
        barmode='overlay'
    )

    fig.update_xaxes(type='category', nticks=10, showgrid=False, row=1, col=1)
    fig.update_xaxes(showgrid=False, showticklabels=False, row=1, col=2)
    fig.update_yaxes(side="right", showgrid=True, gridcolor="rgba(128,128,128,0.15)", row=1, col=2)

    # Зум на колесико
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})


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
        col_chart, col_xray = st.columns([3.1, 0.9])
        with col_chart:
            c1, c2 = st.columns([2, 1])
            crypto_symbol = c1.selectbox("Выберите инструмент", all_crypto,
                                         index=all_crypto.index("BTCUSDT") if "BTCUSDT" in all_crypto else 0,
                                         key="c_sym")
            crypto_tf = c2.selectbox("Таймфрейм графика", ["15 Минут", "1 Час", "1 День"], key="c_tf")

            crypto_df = fetch_hub_candles(crypto_symbol, "crypto", crypto_tf)
            render_native_chart(crypto_df, crypto_symbol)

        with col_xray:
            with st.container(border=True):
                st.markdown(f"#### 🔍 X-RAY АНАЛИЗ\n**{crypto_symbol}**")

                if not crypto_df.empty and len(crypto_df) >= 15:
                    live_price = crypto_df['c'].iloc[-1]
                    rsi_value = ta.momentum.RSIIndicator(crypto_df['c'], window=14).rsi().iloc[-1]

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
            st.dataframe(active_positions, hide_index=True)
        with c_h:
            st.markdown("#### 📜 Журнал сделок Bybit")
            st.dataframe(h_df, hide_index=True)

# ==============================================================================
# 🏛️ ФОНДОВЫЙ-ХАБ (MOEX)
# ==============================================================================
with hub_moex:
    term_m, screen_m, stats_m = st.tabs(["📊 ТЕРМИНАЛ", "🧠 AI-СКРИНЕР", "📈 ПОРТФЕЛЬ И СТАТИСТИКА"])

    with term_m:
        col_chart_m, col_xray_m = st.columns([3.1, 0.9])
        with col_chart_m:
            c1m, c2m = st.columns([2, 1])
            moex_symbol = c1m.selectbox("Выберите акцию", all_moex,
                                        index=all_moex.index("SBER") if "SBER" in all_moex else 0, key="m_sym")
            moex_tf = c2m.selectbox("Таймфрейм графика", ["15 Минут", "1 Час", "1 День"], key="m_tf")

            moex_df = fetch_hub_candles(moex_symbol, "stocks", moex_tf)
            render_native_chart(moex_df, moex_symbol)

        with col_xray_m:
            with st.container(border=True):
                st.markdown(f"#### 🔍 X-RAY АНАЛИЗ\n**{moex_symbol}**")

                if not moex_df.empty and len(moex_df) >= 15:
                    live_price_m = moex_df['c'].iloc[-1]
                    rsi_value_m = ta.momentum.RSIIndicator(moex_df['c'], window=14).rsi().iloc[-1]

                    st.metric("Цена акции", f"{live_price_m:,.2f} ₽")
                    st.metric("Мгновенный RSI", f"{rsi_value_m:.2f}")

                    sma200 = moex_df['c'].mean() if len(moex_df) < 200 else moex_df['c'].rolling(200).mean().iloc[-1]
                    if live_price_m > sma200:
                        st.success("UPTREND 📈 (Выше SMA 200)")
                    else:
                        st.error("DOWNTREND 📉 (Ниже SMA 200)")
                else:
                    st.warning("Ожидание стабильного потока данных...")

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
            st.dataframe(active_positions_m, hide_index=True)
        with c_h_m:
            st.markdown("#### 📜 Журнал сделок MOEX")
            st.dataframe(h_df_m, hide_index=True)