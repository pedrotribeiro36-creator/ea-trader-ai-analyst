import os, time, requests
from fastapi import FastAPI, Request
from apscheduler.schedulers.background import BackgroundScheduler
from analyzer import run_scan

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME   = os.getenv("BOT_USERNAME","")
CHAT_ID_FIXED  = os.getenv("CHAT_ID","")         # opcional
SCAN_EVERY_MIN = int(os.getenv("SCAN_EVERY_MIN","10"))

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = FastAPI()
scheduler = BackgroundScheduler()
scheduler.start()

LAST_CHAT_ID = None

def tg_send(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text})
    except Exception as e:
        print("Send fail:", e)

def broadcast(texts):
    chat_id = CHAT_ID_FIXED or LAST_CHAT_ID
    if not chat_id:
        print("Nenhum chat registado. Usa /start ou define CHAT_ID.")
        return
    for t in texts:
        tg_send(chat_id, t)
        time.sleep(0.4)

@app.post("/webhook")
async def webhook(req: Request):
    global LAST_CHAT_ID
    data = await req.json()
    msg = data.get("message") or data.get("edited_message") or {}
    chat_id = str(((msg.get("chat") or {}).get("id")) or "")
    text = (msg.get("text") or "").strip()
    if chat_id:
        LAST_CHAT_ID = chat_id
    if text == "/start":
        tg_send(chat_id, "👋 Bot ligado.\nComandos:\n/start\n/id\n/signal")
    elif text == "/id":
        tg_send(chat_id, f"chat_id: {chat_id}")
    elif text == "/signal":
        tg_send(chat_id, "🔎 A analisar…")
        broadcast(run_scan())
    else:
        if text:
            tg_send(chat_id, f"Recebi: {text}")
    return {"ok": True}

def scheduled_job():
    try:
        broadcast(run_scan())
    except Exception as e:
        print("job error:", e)

scheduler.add_job(scheduled_job, "interval", minutes=SCAN_EVERY_MIN, id="scan_job", replace_existing=True)

@app.get("/")
def root():
    return {"ok": True}
