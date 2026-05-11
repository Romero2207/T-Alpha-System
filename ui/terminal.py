import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import json
import requests
from pybit.unified_trading import HTTP

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection
from engine.portfolio_manager import PortfolioManager

portfolio = PortfolioManager()

st.set_page_config(page_title="T-Alpha Pro Terminal", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    header {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; font-size: 16px; font-weight: 600; color: #848E9C; }
    .stTabs [aria-selected="true"] { color: #F3BA2F !important; border-bottom: 2px solid #F3BA2F !important; }
    .trade-panel { background-color: #161A25; border: 1px solid #2B3139; border-radius: 4px; padding: 15px; }
    .log-card { background-color: #161A25; border-left: 3px solid #2B3139; padding: 10px; margin-bottom: 8px; font-family: monospace; font-size: 12px;}
    .buy-text { color: #0ECB81 !important; font-weight: bold;}
    .sell-text { color: #F6465D !important; font-weight: bold;}
    div[data-testid="metric-container"] { padding: 5px 0px; }
    .stButton>button { width: 100%; } /* Убрали параметр из питона, перенесли в CSS для кнопок */
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def fetch_live_chart(symbol, market_type):
    """Качает 15-минутные свечи для плотного и красивого графика"""
    df = pd.DataFrame()
    try:
        if market_type == "crypto":
            client = HTTP(testnet=False)
            # Изменили интервал на 15 минут, лимит 500 (~5 дней истории)
            res = client.get_kline(category="linear", symbol=symbol, interval=15, limit=500)
            if res['retCode'] == 0:
                klines = res['result']['list']
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
            else:
                # Мосбиржа: запрашиваем данные ТОЛЬКО за последние 14 дней, чтобы не улететь в 2011 год
                from datetime import datetime, timedelta
                start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
                url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{symbol}/candles.json?iss.meta=off&interval=10&from={start_date}"
                res = requests.get(url, timeout=5).json()
                candles = res['candles']['data']
                cols = res['candles']['columns']
                df = pd.DataFrame(candles, columns=cols)
                df = df.rename(columns={'end': 'timestamp'})
                df['timestamp'] = pd.to_datetime(df['timestamp'])

        if not df.empty:
            df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(
                float)
            df = df.sort_values('timestamp')
    except Exception as e:
        print(f"Ошибка загрузки графика: {e}")
    return df


@st.cache_data(ttl=3600)
def get_all_crypto_symbols():
    try:
        client = HTTP()
        res = client.get_instruments_info(category="linear")
        return sorted([x['symbol'] for x in res['result']['list'] if
                       x['quoteCoin'] == 'USDT' and not x['symbol'].startswith('1000')])
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
    logs = pd.read_sql_query(
        f"SELECT timestamp, ai_decision FROM experience_replay WHERE market_state LIKE '%{asset_symbol}%' ORDER BY id DESC LIMIT 15",
        conn)
    conn.close()

    fiat_bal = f_df.iloc[0]['amount'] if not f_df.empty else 0.0
    asset_bal = a_df.iloc[0]['amount'] if not a_df.empty else 0.0
    avg_entry = a_df.iloc[0]['average_entry_price'] if not a_df.empty and 'average_entry_price' in a_df.columns else 0.0
    return fiat_bal, asset_bal, avg_entry, logs


tab_terminal, tab_ai_screener = st.tabs(["📊 РУЧНОЙ ТЕРМИНАЛ", "🧠 AI-СКРИНЕР (АВТОПИЛОТ)"])

with tab_terminal:
    market_mode = st.radio("Рынок:", ["Криптовалюта (Bybit)", "Фондовый рынок (MOEX)"], horizontal=True,
                           label_visibility="collapsed")

    is_crypto = "Bybit" in market_mode
    market_type = "crypto" if is_crypto else "stocks"
    assets = get_all_crypto_symbols() if is_crypto else get_all_moex_symbols()
    default_asset = "BTCUSDT" if is_crypto else "SBER"
    fiat = "USDT" if is_crypto else "RUB"
    fiat_sign = "$" if is_crypto else "₽"

    col_sel, col_p, col_c, col_b, col_a = st.columns([2, 1, 1, 1, 1])
    with col_sel:
        symbol = st.selectbox("Инструмент", assets, index=assets.index(default_asset) if default_asset in assets else 0,
                              label_visibility="collapsed")

    df_chart = fetch_live_chart(symbol, market_type)
    fiat_bal, asset_bal, avg_entry, df_logs = load_user_portfolio(fiat, symbol)

    if not df_chart.empty:
        current_price = df_chart['close'].iloc[-1]
        change_pct = ((current_price - df_chart['open'].iloc[0]) / df_chart['open'].iloc[0]) * 100
    else:
        current_price, change_pct = 0.0, 0.0

    with col_p:
        st.metric("Цена", f"{fiat_sign}{current_price:,.2f}")
    with col_c:
        st.metric("Динамика", f"{change_pct:+.2f}%", delta_color="normal" if change_pct >= 0 else "inverse")
    with col_b:
        st.metric(f"Свободно ({fiat})", f"{fiat_sign}{fiat_bal:,.2f}")
    with col_a:
        st.metric(f"В позиции ({symbol})", f"{asset_bal:.4f}")

    st.markdown("<hr style='margin: 5px 0 10px 0; border-color: #2B3139;'>", unsafe_allow_html=True)

    main_col, side_col = st.columns([3, 1])

    with main_col:
        if not df_chart.empty:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
            fig.add_trace(go.Candlestick(
                x=df_chart['timestamp'], open=df_chart['open'], high=df_chart['high'], low=df_chart['low'],
                close=df_chart['close'],
                increasing_line_color='#0ECB81', decreasing_line_color='#F6465D', name='Цена'
            ), row=1, col=1)

            colors = ['#0ECB81' if row['close'] >= row['open'] else '#F6465D' for idx, row in df_chart.iterrows()]
            fig.add_trace(go.Bar(x=df_chart['timestamp'], y=df_chart['volume'], marker_color=colors, name='Объем'),
                          row=2, col=1)

            fig.update_layout(
                height=600, margin=dict(l=0, r=50, t=10, b=0), plot_bgcolor='#0B0E14', paper_bgcolor='#0B0E14',
                xaxis_rangeslider_visible=False, showlegend=False, dragmode='pan'
            )

            # Настройка осей и схлопывание дыр для Фондового рынка
            fig.update_yaxes(showgrid=True, gridcolor='#1F242F', side="right", row=1)
            fig.update_yaxes(showgrid=False, showticklabels=False, row=2)

            if market_type == "stocks":
                # Скрываем нерабочие часы Мосбиржи (с 19:00 до 10:00) и выходные (Суббота-Воскресенье)
                hide_breaks = [
                    dict(bounds=["sat", "mon"]),
                    dict(bounds=[19, 10], pattern="hour")
                ]
                fig.update_xaxes(showgrid=True, gridcolor='#1F242F', rangebreaks=hide_breaks, row=1)
                fig.update_xaxes(showgrid=True, gridcolor='#1F242F', rangebreaks=hide_breaks, row=2)
            else:
                fig.update_xaxes(showgrid=True, gridcolor='#1F242F', row=2)

            # Избавились от желтых ошибок use_container_width
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})
        else:
            st.warning("Ожидание данных от API биржи...")

        st.markdown("#### ОТКРЫТЫЕ ПОЗИЦИИ")
        if asset_bal > 0:
            unrealized_pnl = (current_price - avg_entry) * asset_bal
            pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0
            pnl_color = "#0ECB81" if unrealized_pnl >= 0 else "#F6465D"
            pnl_sign = "+" if unrealized_pnl >= 0 else ""

            st.markdown(f"""
            <table style="width:100%; text-align:left; color:#848E9C; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #2B3139;"><th>Инструмент</th><th>Кол-во</th><th>Цена входа</th><th>Текущая цена</th><th>Нереализованный PnL</th></tr>
                <tr>
                    <td style="padding: 10px; color:#EAECEF; font-weight:bold;">{symbol}</td>
                    <td style="color:#EAECEF;">{asset_bal:.4f}</td>
                    <td>{fiat_sign}{avg_entry:,.2f}</td><td>{fiat_sign}{current_price:,.2f}</td>
                    <td style="color:{pnl_color}; font-weight:bold;">{pnl_sign}{fiat_sign}{unrealized_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)</td>
                </tr>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#848E9C;'>Нет активных позиций.</div>", unsafe_allow_html=True)

    with side_col:
        st.markdown("<div class='trade-panel'>", unsafe_allow_html=True)
        st.markdown("##### РУЧНОЙ ОРДЕР (MARKET)")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🟢 BUY", key="buy_btn"):
                portfolio.execute_paper_trade(symbol, "BUY", current_price)
                st.rerun()
        with b2:
            if st.button("🔴 SELL", key="sell_btn"):
                portfolio.execute_paper_trade(symbol, "SELL", current_price)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

with tab_ai_screener:
    st.header("🌐 ГЛОБАЛЬНЫЙ СКАНЕР РЫНКА (АВТОПИЛОТ)")
    st.markdown(
        "<div style='color: #848E9C; margin-bottom: 20px;'>Нейросеть непрерывно сканирует рынок. Бот самостоятельно совершает сделки, если они проходят фильтры Риск-Менеджера.</div>",
        unsafe_allow_html=True)

    col_upd, _ = st.columns([1, 5])
    with col_upd:
        if st.button("🔄 Обновить радар"):
            st.rerun()

    conn = get_connection()
    df_signals = pd.read_sql_query(
        "SELECT timestamp, market_state, ai_decision FROM experience_replay WHERE market_state LIKE '%аномалия%' ORDER BY id DESC LIMIT 20",
        conn)
    conn.close()

    if not df_signals.empty:
        for index, row in df_signals.iterrows():
            try:
                dec = json.loads(row['ai_decision'])
                action = dec.get("action", "HOLD")
                conf = dec.get("confidence", 0)
                reason = dec.get("reason", "Анализ завершен")
                price = dec.get("current_price", 0.0)
                change = dec.get("market_change", 0.0)
                tp = dec.get("take_profit", 0.0)
                sl = dec.get("stop_loss", 0.0)

                state = row['market_state']
                symbol = state.split("Актив ")[1].split(".")[0]

                icon = "🟢" if "BUY" in action and "Blocked" not in action else "🔴" if "SELL" in action and "Blocked" not in action else "⚪"

                with st.expander(
                        f"{icon} {row['timestamp']} | {symbol} | {action} ({conf}%) | Изменение: {change:+.2f}%"):
                    st.write(f"**Обоснование ИИ:** {reason}")

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Цена входа", f"${price:,.4f}")

                    tp_color = "normal" if tp > price else "off"
                    m2.metric("Take Profit", f"${tp:,.4f}" if tp > 0 else "N/A",
                              delta=f"{((tp - price) / price) * 100:.2f}%" if tp > 0 else None, delta_color=tp_color)

                    sl_color = "inverse" if sl < price else "off"
                    m3.metric("Stop Loss", f"${sl:,.4f}" if sl > 0 else "N/A",
                              delta=f"{((sl - price) / price) * 100:.2f}%" if sl > 0 else None, delta_color=sl_color)

                    m4.metric("Уверенность", f"{conf}%")

                    if st.button(f"Торговать {symbol} вручную", key=f"force_trade_{index}_{symbol}"):
                        st.info("Перейдите во вкладку 'Ручной Терминал' для точного исполнения.")
            except Exception as e:
                pass
    else:
        st.info("Радар пока не обнаружил аномалий. Движок data_collector.py анализирует рынок...")
