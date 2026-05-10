import streamlit as st
import pandas as pd
import sys
import os
import json
import base64

# Фикс путей для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.market_gateway import MarketGateway
from ai.sentiment import SentimentAnalyzer
from ai.gigachat_api import GigaChatInterface

st.set_page_config(page_title="T-ALPHA CORE", layout="wide", initial_sidebar_state="collapsed")

gateway = MarketGateway()
analyzer = SentimentAnalyzer()
ai_brain = GigaChatInterface()

# Глобальный CSS
st.markdown("""
    <style>
    .block-container { padding-top: 0rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; border-bottom: 1px solid #1f2937; }
    .stTabs [data-baseweb="tab"] { height: 35px; font-size: 12px; }
    h1 { font-size: 1.4rem !important; color: #2962ff; margin-bottom: 10px; }
    /* Убираем отступы у iframe */
    iframe { border: none !important; }
    </style>
""", unsafe_allow_html=True)


def render_tv_chart(df):
    if df is None or df.empty:
        st.warning("Ожидание данных для отрисовки...")
        return

    chart_df = df.copy()
    chart_df['time'] = chart_df['Time'].astype(int) // 10 ** 9
    json_data = chart_df[['time', 'Open', 'High', 'Low', 'Close']].rename(
        columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'}
    ).to_json(orient='records')

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; background:#0d1117; overflow:hidden;">
        <div id="chart" style="width:100vw; height:500px;"></div>
        <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
        <script>
            const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
                layout: {{ background: {{ color: '#0d1117' }}, textColor: '#d1d4dc' }},
                grid: {{ vertLines: {{ color: '#1f2937' }}, horzLines: {{ color: '#1f2937' }} }},
                timeScale: {{ timeVisible: true, borderColor: '#1f2937' }},
                handleScroll: true, handleScale: true,
            }});
            const candles = chart.addCandlestickSeries({{ upColor: '#26a69a', downColor: '#ef5350' }});
            candles.setData({json_data});
            chart.timeScale().fitContent();
        </script>
    </body>
    </html>
    """
    b64_html = base64.b64encode(html_code.encode()).decode()
    st.iframe(f"data:text/html;base64,{b64_html}", height=520)


def run_terminal(m_type):
    col_side, col_main, col_ai = st.columns([1, 4, 1.2])

    with col_side:
        st.caption("УПРАВЛЕНИЕ")
        if m_type == "CRYPTO":
            symbols = gateway.get_crypto_symbols()
            symbol = st.selectbox("ПАРА", symbols, key=f"s_{m_type}")
            figi = None
        else:
            stocks = gateway.get_stock_assets()
            symbol = st.selectbox("АКЦИЯ", list(stocks.keys()), key=f"s_{m_type}")
            figi = stocks[symbol]

        st.number_input("ДЕПОЗИТ", value=1000, key=f"d_{m_type}")
        st.slider("РИСК %", 0.1, 5.0, 1.0, key=f"r_{m_type}")
        live = st.toggle("ЖИВОЕ ОБНОВЛЕНИЕ", value=True, key=f"l_{m_type}")

    with col_main:
        df = gateway.get_ohlc(symbol, "Крипто" if m_type == "CRYPTO" else "Фондовый")
        render_tv_chart(df)
        st.caption("ЖУРНАЛ ОПЕРАЦИЙ")
        # ИСПРАВЛЕНО: width='stretch' вместо None
        st.dataframe(pd.DataFrame(columns=["Время", "Тип", "Цена"]), width='stretch')

    with col_ai:
        st.subheader("🧠 АНАЛИТИКА")

        @st.fragment(run_every=10 if live else None)
        def update_ai():
            try:
                price = gateway.get_price(symbol, "Крипто" if m_type == "CRYPTO" else "Фондовый", figi)
                st.metric("ЦЕНА", f"${price:,.2f}")

                # Формируем контекст для ИИ
                context = df.tail(5).to_json() if (df is not None and not df.empty) else "No data"
                prediction = ai_brain.get_prediction(context)

                with st.container(border=True):
                    st.write(f"**ВЕРДИКТ:** {prediction}")
            except Exception as e:
                st.error(f"Ошибка обновления: {e}")

        update_ai()


# Основной интерфейс
st.title("T-ALPHA v1.0")
t1, t2 = st.tabs(["⚡ КРИПТОВАЛЮТНЫЙ ТЕРМИНАЛ", "📈 ФОНДОВЫЙ ТЕРМИНАЛ"])

with t1:
    run_terminal("CRYPTO")
with t2:
    run_terminal("STOCKS")