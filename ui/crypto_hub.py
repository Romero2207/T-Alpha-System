import streamlit as st
import sys
import os
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection

st.header("CRYPTO HUB // BYBIT TESTNET")

def load_data():
    conn = get_connection()
    query = "SELECT timestamp, price, volume FROM market_data WHERE symbol='BTCUSDT' ORDER BY id DESC LIMIT 50"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

data = load_data()

if not data.empty:
    st.dataframe(data, use_container_width=True)
    st.line_chart(data.set_index('timestamp')['price'])
else:
    st.warning("No data in DB. Ensure data_collector.py is running.")