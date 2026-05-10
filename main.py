import streamlit as st

# Конфигурация интерфейса
st.set_page_config(
    page_title="T-ALPHA | HYBRID TERMINAL",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Описание структуры страниц
pages = {
    "Рынки": [
        st.Page("ui/crypto_hub.py", title="⚡ Крипто-центр", icon="💎"),
        st.Page("ui/stocks_hub.py", title="📈 Фондовый отдел", icon="🏢"),
    ],
    "Интеллект": [
        st.Page("ui/ai_training.py", title="🧠 Обучение и Память", icon="🧬"),
        st.Page("ui/strategy_lab.py", title="🔬 Лаборатория стратегий", icon="🧪"),
    ],
    "Настройки": [
        st.Page("ui/api_config.py", title="🔑 API Ключи и Шлюзы", icon="🛡️"),
    ]
}

# Запуск навигации-
pg = st.navigation(pages)

# Общий стиль (Dark Finance Mode)
st.markdown("""
    <style>
    .stApp { background-color: #010409; color: #e6edf3; }
    [data-testid="stSidebar"] { background-color: #0d1117; border-right: 1px solid #30363d; }
    </style>
""", unsafe_allow_html=True)

pg.run()