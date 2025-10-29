import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
import httpx

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Falta a env TELEGRAM_TOKEN")

# Render dá-nos a URL pública nesta env quando está live
PUBLIC_URL = os.environ.get("RENDER_EXTERNAL_URL")  # ex.: https://ea-trader-ai-analyst.onrender.com
WEBHOOK_PATH = f"/webhook/{TOKEN}"                  # simples “segredo” do webhook
WEBHOOK_URL = (PUBLIC_URL + WEBHOOK_PATH) if PUBLIC_URL else None

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()


async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(f"{TELEGRAM_API}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


@app.on_event("startup")
async def setup_webhook():
    """Define o webhook quando a app arranca (quando a PUBLIC_URL já existe)."""
    if not WEBHOOK_URL:
        # Em arranques muito iniciais, a env pode vir vazia. Tentamos mais tarde.
        return

    async with httpx.AsyncClient(timeout=20) as client:
        # Remove qualquer webhook anterior (opcional)
        await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": ""})
        # Define o nosso webhook
        r = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": WEBHOOK_URL})
        ok = r.json().get("ok")
        if not ok:
            # Apenas para veres nos logs se algo falhar
            print("Falha ao definir webhook:", r.text)


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    """Recebe updates do Telegram."""
    if not TOKEN:
        raise HTTPException(status_code=500, detail="Sem TOKEN")

    data = await request.json()

    # Só lidamos com mensagens de texto simples
    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return {"ok": True}

    # Comandos básicos
    if text.lower().startswith("/start"):
        await send_message(chat_id, "👋 Olá! O bot está online.\nPodes escrever /help para ver opções.")
    elif text.lower().startswith("/help"):
        await send_message(chat_id, "Comandos:\n/start – verificar se estou online\n/help – esta ajuda")
    else:
        # Eco simples (podes trocar por lógica do teu projeto)
        await send_message(chat_id, f"Recebi: {text}")

    return {"ok": True}
