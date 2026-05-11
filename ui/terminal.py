import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
import json
import requests
from pybit.unified_trading import HTTP

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection
from engine.portfolio_manager import PortfolioManager

portfolio = PortfolioManager()

# --- НАСТРОЙКИ СТРАНИЦЫ И CSS ---
st.set_page_config(page_title="T-Alpha Terminal", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; max-width: 100%; }
    header {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; font-size: 16px; font-weight: 600; color: #848E9C; }
    .stTabs [aria-selected="true"] { color: #F3BA2F !important; border-bottom: 2px solid #F3BA2F !important; }
    .trade-panel { background-color: #161A25; border: 1px solid #2B3139; border-radius: 4px; padding: 15px; }
    .log-card { background-color: #161A25; border-left: 3px solid #2B3139; padding: 8px 12px; margin-bottom: 8px; font-family: monospace; font-size: 12px; line-height: 1.2;}
    .buy-text { color: #0ECB81 !important; font-weight: bold;}
    .sell-text { color: #F6465D !important; font-weight: bold;}
    .hold-text { color: #848E9C !important;}
    div[data-testid="metric-container"] { padding: 5px 0px; }
</style>
""", unsafe_allow_html=True)


# --- ФУНКЦИИ БАЗЫ ДАННЫХ И API ---
@st.cache_data(ttl=3600)
def get_all_crypto_symbols():
    try:
        client = HTTP()
        res = client.get_instruments_info(category="linear")
        # Фильтруем всякий мусор, оставляем только чистые пары к USDT
        symbols = [x['symbol'] for x in res['result']['list'] if
                   x['quoteCoin'] == 'USDT' and not x['symbol'].startswith('1000')]
        return sorted(symbols)
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@st.cache_data(ttl=3600)
def get_all_moex_symbols():
    try:
        url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json?iss.only=securities"
        res = requests.get(url, timeout=5).json()
        return sorted([x[0] for x in res['securities']['data']])
    except:
        return ["SBER", "GAZP", "LKOH", "YNDX"]


def load_market_data(symbol, tf='1min'):
    conn = get_connection()
    # Увеличили лимит истории для зума
    df = pd.read_sql_query(
        f"SELECT timestamp, price, volume FROM market_data WHERE symbol='{symbol}' ORDER BY id DESC LIMIT 5000", conn)
    conn.close()

    if df.empty:
        return df, 0.0, 0.0

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    current_price = df['price'].iloc[-1]

    first_price = df['price'].iloc[0]
    change_pct = ((current_price - first_price) / first_price) * 100 if first_price > 0 else 0.0

    df.set_index('timestamp', inplace=True)
    ohlc = df['price'].resample(tf).ohlc().dropna()
    ohlc.reset_index(inplace=True)

    return ohlc, current_price, change_pct


def load_user_data(fiat_symbol, asset_symbol):
    conn = get_connection()
    f_df = pd.read_sql_query(f"SELECT amount FROM portfolio WHERE symbol='{fiat_symbol}'", conn)
    a_df = pd.read_sql_query(f"SELECT amount, average_entry_price FROM portfolio WHERE symbol='{asset_symbol}'", conn)
    logs = pd.read_sql_query(
        f"SELECT timestamp, ai_decision FROM experience_replay WHERE market_state LIKE '%{asset_symbol}%' ORDER BY id DESC LIMIT 20",
        conn)
    conn.close()

    fiat_bal = f_df.iloc[0]['amount'] if not f_df.empty else 0.0
    asset_bal = a_df.iloc[0]['amount'] if not a_df.empty else 0.0
    # Достаем среднюю цену входа (если нет, то 0)
    avg_entry = a_df.iloc[0]['average_entry_price'] if not a_df.empty and 'average_entry_price' in a_df.columns else 0.0

    # Исправлено: возвращаем logs
    return fiat_bal, asset_bal, avg_entry, logs


# --- ГЛАВНЫЙ ИНТЕРФЕЙС ---
tab_crypto, tab_stocks = st.tabs(["🪙 КРИПТОВАЛЮТА (BYBIT)", "🏛️ ФОНДОВЫЙ РЫНОК (MOEX)"])


def render_trading_interface(market_type):
    if market_type == "crypto":
        assets = get_all_crypto_symbols()
        default_index = assets.index("BTCUSDT") if "BTCUSDT" in assets else 0
        fiat = "USDT"
        fiat_sign = "$"
    else:
        assets = get_all_moex_symbols()
        default_index = assets.index("SBER") if "SBER" in assets else 0
        fiat = "RUB"
        fiat_sign = "₽"

    col_sel, col_btn, col_p, col_c, col_b, col_a = st.columns([1.5, 1, 1, 1, 1, 1])
    with col_sel:
        symbol = st.selectbox("Инструмент", assets, index=default_index, label_visibility="collapsed")

    with col_btn:
        if st.button(f"➕ Отслеживать", key=f"track_{symbol}_{market_type}", use_container_width=True):
            conn = get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO watchlist (symbol, market_type) VALUES (?, ?)", (symbol, market_type))
                conn.commit()
                st.toast(f"✅ {symbol} добавлен в ядро сбора данных!")
            except:
                st.toast(f"ℹ️ {symbol} уже отслеживается.")
            conn.close()

    df_candles, current_price, change_pct = load_market_data(symbol)
    fiat_bal, asset_bal, avg_entry, df_logs = load_user_data(fiat, symbol)

    change_color = "normal" if change_pct >= 0 else "inverse"
    with col_p:
        st.metric("Цена", f"{fiat_sign}{current_price:,.2f}")
    with col_c:
        # Если динамика сломана старыми данными, показываем прочерк
        display_change = f"{change_pct:+.2f}%" if change_pct > -90 else "N/A"
        st.metric("Динамика (24h)", display_change, delta_color=change_color if change_pct > -90 else "off")
    with col_b:
        st.metric(f"Доступно ({fiat})", f"{fiat_sign}{fiat_bal:,.2f}")
    with col_a:
        st.metric(f"Позиция ({symbol})", f"{asset_bal:.4f}")

    st.markdown("<hr style='margin: 5px 0 10px 0; border-color: #2B3139;'>", unsafe_allow_html=True)

    main_col, side_col = st.columns([3, 1])

    with main_col:
        if not df_candles.empty:
            # 1. МАГИЯ ЗДЕСЬ: Отрезаем старые грязные данные ДО передачи в график.
            # Оставляем только 150 самых свежих свечей.
            chart_data = df_candles.tail(150)

            # 2. Передаем в Plotly ТОЛЬКО чистые данные (chart_data)
            fig = go.Figure(data=[go.Candlestick(
                x=chart_data['timestamp'],
                open=chart_data['open'], high=chart_data['high'],
                low=chart_data['low'], close=chart_data['close'],
                increasing_line_color='#0ECB81', decreasing_line_color='#F6465D'
            )])

            # 3. Настройки интерфейса (убрали жесткий range, Plotly сам идеально смасштабирует чистые данные)
            fig.update_layout(
                height=550, margin=dict(l=0, r=50, t=0, b=0),
                plot_bgcolor='#0B0E14', paper_bgcolor='#0B0E14',
                xaxis_rangeslider_visible=False,
                dragmode='pan',  # Левая кнопка мыши перемещает
                xaxis=dict(showgrid=True, gridcolor='#1F242F'),
                yaxis=dict(showgrid=True, gridcolor='#1F242F', side="right", fixedrange=False, autorange=True)
            )

            # Включаем зум колесиком и отключаем назойливую верхнюю панель инструментов
            st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': False})
        else:
            st.info(f"Нет данных по {symbol}. Нажмите '➕ Отслеживать' и подождите.")

        # --- ТАБЛИЦА PnL (Оставляем без изменений) ---
        st.markdown("#### ОТКРЫТЫЕ ПОЗИЦИИ")
        if asset_bal > 0:
            unrealized_pnl = (current_price - avg_entry) * asset_bal
            pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry > 0 else 0

            pnl_color = "#0ECB81" if unrealized_pnl >= 0 else "#F6465D"
            pnl_sign = "+" if unrealized_pnl >= 0 else ""

            st.markdown(f"""
            <table style="width:100%; text-align:left; color:#848E9C; border-collapse: collapse;">
                <tr style="border-bottom: 1px solid #2B3139;">
                    <th style="padding: 10px;">Инструмент</th>
                    <th>Кол-во</th>
                    <th>Цена входа</th>
                    <th>Текущая цена</th>
                    <th>Нереализованный PnL</th>
                </tr>
                <tr>
                    <td style="padding: 10px; color:#EAECEF; font-weight:bold;">{symbol}</td>
                    <td style="color:#EAECEF;">{asset_bal:.4f}</td>
                    <td>{fiat_sign}{avg_entry:,.2f}</td>
                    <td>{fiat_sign}{current_price:,.2f}</td>
                    <td style="color:{pnl_color}; font-weight:bold;">{pnl_sign}{fiat_sign}{unrealized_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)</td>
                </tr>
            </table>
            """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='color:#848E9C;'>Нет активных позиций. Выставьте ордер BUY.</div>",
                        unsafe_allow_html=True)

    with side_col:
        st.markdown("<div class='trade-panel'>", unsafe_allow_html=True)
        st.markdown("##### РУЧНОЙ ОРДЕР (MARKET)")

        b1, b2 = st.columns(2)
        with b1:
            if st.button("🟢 BUY", use_container_width=True, key=f"buy_{symbol}_{market_type}"):
                portfolio.execute_paper_trade(symbol, "BUY", current_price)
                st.rerun()
        with b2:
            if st.button("🔴 SELL", use_container_width=True, key=f"sell_{symbol}_{market_type}"):
                portfolio.execute_paper_trade(symbol, "SELL", current_price)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("##### ПОТОК ИИ (BRAIN)")
        log_container = st.container(height=420)
        with log_container:
            for index, row in df_logs.iterrows():
                try:
                    dec = json.loads(row['ai_decision'])
                    action = dec.get("action", "HOLD")
                    css = "buy-text" if "BUY" in action else "sell-text" if "SELL" in action else "hold-text"
                    time_str = str(row['timestamp']).split(' ')[-1]
                    st.markdown(f"""
                    <div class="log-card">
                        <span style="color: #474D57;">{time_str}</span> | 
                        <span class="{css}">{action}</span> <span style="color:#474D57">({dec.get('confidence', 0)}%)</span>
                        <div style="color: #B7BDC6; margin-top: 2px;">{dec.get('reason', '')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    pass


with tab_crypto:
    render_trading_interface("crypto")

with tab_stocks:
    render_trading_interface("stocks")