import requests
import os
import time

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_alert(message):
    if TELEGRAM_TOKEN and CHAT_ID:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}")

# Simulação de alerta
while True:
    send_alert("🚨 Oportunidade de compra encontrada! Verifica o Futbin.")
    time.sleep(3600)  # repete a cada hora
