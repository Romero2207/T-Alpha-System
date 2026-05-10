import streamlit as st
import pandas as pd
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory import get_connection


def load_market_data():
    conn = get_connection()
    query = "SELECT timestamp, price, volume, latency_ms FROM market_data WHERE symbol='BTCUSDT' ORDER BY id DESC LIMIT 100"
    df = pd.read_sql_query(query, conn)
    conn.close()
    if not df.empty:
        df = df.sort_values('timestamp')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        # Русифицируем названия колонок только для визуального отображения
        df.index.name = 'Время'
        df = df.rename(columns={
            'price': 'Цена ($)',
            'volume': 'Объем (24ч)',
            'latency_ms': 'Задержка (мс)'
        })
    return df


def load_brain_logs():
    conn = get_connection()
    query = "SELECT timestamp, ai_decision FROM experience_replay ORDER BY id DESC LIMIT 10"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


st.header("КРИПТО ХАБ // BTCUSDT (ОСНОВНАЯ СЕТЬ)")

if st.button("🔄 СИНХРОНИЗИРОВАТЬ ДАННЫЕ"):
    st.rerun()

st.markdown("---")

market_data = load_market_data()
brain_logs = load_brain_logs()

if not market_data.empty:
    # Немного расширили правую колонку для длинных русских слов (было 2 и 1, стало 1.5 и 1)
    col1, col2 = st.columns([1.5, 1])

    with col1:
        st.subheader("ДИНАМИКА ЦЕНЫ")
        st.line_chart(market_data['Цена ($)'], height=400, use_container_width=True)

        st.subheader("СЫРЫЕ ДАННЫЕ РЫНКА")
        st.dataframe(market_data.sort_index(ascending=False).head(5), use_container_width=True)

    with col2:
        st.subheader("АКТИВНОСТЬ ИИ (МОЗГ)")
        if not brain_logs.empty:
            # Словари для перевода системных команд на русский
            action_ru = {
                "BUY": "ПОКУПКА",
                "SELL": "ПРОДАЖА",
                "HOLD": "ОЖИДАНИЕ",
                "UNKNOWN": "НЕИЗВЕСТНО"
            }

            for index, row in brain_logs.iterrows():
                time_str = row['timestamp']
                try:
                    decision = json.loads(row['ai_decision'])
                    # Получаем команду и сразу переводим её
                    raw_action = decision.get("action", "UNKNOWN")
                    action = action_ru.get(raw_action, raw_action)

                    conf = decision.get("confidence", 0)
                    reason = decision.get("reason", "Нет данных")

                    if raw_action == "BUY":
                        color = "#2ea043"  # Мягкий зеленый (Github Style)
                    elif raw_action == "SELL":
                        color = "#f85149"  # Мягкий красный
                    else:
                        color = "#8b949e"  # Серый

                    st.markdown(f"""
                    <div style="border: 1px solid #30363d; padding: 12px; border-radius: 6px; margin-bottom: 12px; background-color: #0d1117;">
                        <span style="color: #8b949e; font-size: 0.8em;">{time_str}</span><br>
                        <strong style="color: {color}; font-size: 1.1em;">{action}</strong> 
                        <span style="color: #c9d1d9; font-size: 0.9em;">(Уверенность: {conf}%)</span><br>
                        <span style="color: #8b949e; font-size: 0.9em;">Причина: {reason}</span>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    st.write(f"{time_str} | Ошибка чтения лога")
        else:
            st.info("Ожидание данных от нейросети...")

else:
    st.warning("СИСТЕМА: Рыночные данные не найдены. Убедитесь, что engine/data_collector.py запущен.")