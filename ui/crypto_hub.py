import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection

# --- CSS АНИМАЦИИ И СТИЛИЗАЦИЯ (Bybit / Tinkoff Style) ---
st.markdown("""
<style>
    /* Плавный hover-эффект для карточек */
    div[data-testid="metric-container"] {
        background: linear-gradient(145deg, #1e222d 0%, #131722 100%);
        border: 1px solid #2B3139;
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(243, 186, 47, 0.15); /* Легкое золотое свечение */
    }
    .log-card {
        background-color: #131722;
        border-left: 4px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 12px;
        transition: background-color 0.2s;
    }
    .log-card:hover { background-color: #1e222d; }
    .buy-color { color: #00C853 !important; font-weight: bold;}
    .sell-color { color: #FF3D00 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)


# --- ЗАГРУЗКА ДАННЫХ ---
def load_data():
    conn = get_connection()
    # Загрузка рынка
    df_market = pd.read_sql_query(
        "SELECT timestamp, price, volume FROM market_data WHERE symbol='BTCUSDT' ORDER BY id DESC LIMIT 100", conn)
    # Загрузка баланса
    df_balance = pd.read_sql_query("SELECT amount FROM portfolio WHERE symbol='USDT'", conn)
    usdt_balance = df_balance.iloc[0]['amount'] if not df_balance.empty else 0.0

    df_btc = pd.read_sql_query("SELECT amount FROM portfolio WHERE symbol='BTCUSDT'", conn)
    btc_balance = df_btc.iloc[0]['amount'] if not df_btc.empty else 0.0

    # Загрузка логов ИИ
    df_logs = pd.read_sql_query(
        "SELECT timestamp, ai_decision FROM experience_replay WHERE market_state LIKE '%BTCUSDT%' ORDER BY id DESC LIMIT 8",
        conn)
    conn.close()

    if not df_market.empty:
        df_market = df_market.sort_values('timestamp')
    return df_market, usdt_balance, btc_balance, df_logs


df_market, usdt_balance, btc_balance, df_logs = load_data()

# --- ВЕРХНЯЯ ПАНЕЛЬ (БАЛАНСЫ) ---
st.header("⚡ BTCUSDT // ТОРГОВЫЙ ТЕРМИНАЛ")

# Метрики портфеля
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="ДОСТУПНО (USDT)", value=f"${usdt_balance:,.2f}")
with col2:
    st.metric(label="В АКТИВАХ (BTC)", value=f"{btc_balance:.4f} ₿")
with col3:
    current_price = df_market['price'].iloc[-1] if not df_market.empty else 0
    total_equity = usdt_balance + (btc_balance * current_price)
    # Показываем общий капитал. Если больше стартовых 10k - зеленым (profit)
    delta = total_equity - 10000
    st.metric(label="ОБЩИЙ КАПИТАЛ", value=f"${total_equity:,.2f}", delta=f"${delta:,.2f}")

st.markdown("---")

# --- ГРАФИКИ И ЛОГИ ---
if not df_market.empty:
    chart_col, log_col = st.columns([2, 1])

    with chart_col:
        st.subheader("📊 ИНТЕРАКТИВНЫЙ ГРАФИК")

        # Создаем красивый график Plotly
        fig = go.Figure()
        # Линия цены с заливкой градиентом
        fig.add_trace(go.Scatter(
            x=df_market['timestamp'],
            y=df_market['price'],
            mode='lines',
            line=dict(color='#F3BA2F', width=3),  # Цвет Binance/Bybit
            fill='tozeroy',
            fillcolor='rgba(243, 186, 47, 0.1)',
            name='Цена BTC'
        ))

        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(showgrid=False, color='#8b949e'),
            yaxis=dict(showgrid=True, gridcolor='#2B3139', color='#8b949e'),
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)

    with log_col:
        st.subheader("🧠 ЖУРНАЛ ИИ")
        for index, row in df_logs.iterrows():
            try:
                dec = json.loads(row['ai_decision'])
                action = dec.get("action", "HOLD")
                conf = dec.get("confidence", 0)
                reason = dec.get("reason", "")

                # Стилизация текста
                css_class = "buy-color" if "BUY" in action else "sell-color" if "SELL" in action else ""

                st.markdown(f"""
                <div class="log-card">
                    <div style="font-size: 0.8rem; color: #8b949e; margin-bottom: 5px;">{row['timestamp']}</div>
                    <div style="font-size: 1.2rem;" class="{css_class}">{action} <span style="font-size:0.9rem; color:#8b949e;">({conf}%)</span></div>
                    <div style="font-size: 0.9rem; margin-top: 5px; color: #c9d1d9;">{reason}</div>
                </div>
                """, unsafe_allow_html=True)
            except:
                pass
else:
    st.info("Ожидание данных с рынка...")