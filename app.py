from fastapi import FastAPI, Request, HTTPException
import os
import requests

app = FastAPI()

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]  # mesmo nome que tens no Render

@app.get("/")
def home():
    return {"ok": True, "status": "EA Trader AI online"}

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    # valida o token do caminho
    if token != BOT_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")

    update = await request.json()
    chat_id = None
    text = None

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
    elif "edited_message" in update:
        chat_id = update["edited_message"]["chat"]["id"]
        text = update["edited_message"].get("text", "")

    if chat_id and text:
        if text.startswith("/start"):
            msg = "👋 Olá! O bot está online.\nPodes escrever /help para ver opções."
        elif text.startswith("/help"):
            msg = "Comandos:\n/start – verificar se estou online\n/help – esta ajuda"
        else:
            msg = f"Recebi: {text}"

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": msg}
        )

    return {"ok": True}
