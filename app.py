import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="EA Trader AI – Analyst", page_icon="📈", layout="wide")

st.title("📊 EA Trader AI – Analyst")
st.markdown("Sistema de alertas automáticos para FUTBIN e leaks do FUT Sheriff.")

data = [
    {"Jogador": "Vinicius Jr", "Preço Atual": 125000, "Tendência 24h": -12, "Liquidez": 30, "Target Sell": 138000},
    {"Jogador": "Rodri 87", "Preço Atual": 23000, "Tendência 24h": -10, "Liquidez": 15, "Target Sell": 28000}
]
df = pd.DataFrame(data)
st.dataframe(df, use_container_width=True)

st.success("✅ Sistema ativo! O bot enviará alertas no Telegram quando encontrar oportunidades.")
