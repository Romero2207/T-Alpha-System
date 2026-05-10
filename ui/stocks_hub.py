import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection

def load_stock_data():
    conn = get_connection()
    query = "SELECT timestamp, price, volume, latency_ms FROM market_data WHERE symbol='SBER' ORDER BY id DESC LIMIT 100"
    df = pd.read_sql_query(query, conn)
    conn.close()
    if not df.empty:
        df = df.sort_values('timestamp')
        df = df.rename(columns={'price': 'Цена (₽)', 'volume': 'Объем', 'latency_ms': 'Задержка (мс)'})
        df.set_index('timestamp', inplace=True)
    return df

st.header("ФОНДОВЫЙ ХАБ // МОСКОВСКАЯ БИРЖА (MOEX)")

if st.button("🔄 ОБНОВИТЬ ДАННЫЕ АКЦИЙ"):
    st.rerun()

data = load_stock_data()

if not data.empty:
    st.subheader("ДИНАМИКА ЦЕНЫ: СБЕРБАНК")
    st.line_chart(data['Цена (₽)'], height=400)
    st.dataframe(data.sort_index(ascending=False).head(10), use_container_width=True)
else:
    st.info("Данные по акциям еще не собраны. Запустите engine/data_collector.py")