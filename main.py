import streamlit as st

# Конфигурация окна (должна быть первым вызовом)
st.set_page_config(
    page_title="T-Alpha-System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Инъекция строгих стилей (Dark Finance & Monospace)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Roboto Mono', monospace !important;
    }
    .stApp {
        background-color: #0D1117;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #C9D1D9 !important;
        font-weight: 700 !important;
    }
    p, span, div {
        color: #8B949E !important;
    }
    </style>
""", unsafe_allow_html=True)

# Главный заголовок
st.title("T-ALPHA-SYSTEM // COMMAND CENTER")
st.markdown("---")

# Настройка навигации
pages = {
    "MARKET HUBS": [
        st.Page("ui/crypto_hub.py", title="Crypto Hub"),
        st.Page("ui/stocks_hub.py", title="Stocks Hub"),
    ],
    "SYSTEM & LOGIC": [
        st.Page("ui/ai_training.py", title="AI Training & Memory"),
    ]
}

pg = st.navigation(pages)
pg.run()