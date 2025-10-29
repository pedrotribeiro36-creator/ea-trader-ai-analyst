# app.py
import os, json, asyncio, logging
from typing import Dict, Any, List
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import aiohttp

from scheduler import start_scheduler, stop_scheduler, get_scheduler_status
from market_analyzer import analyze_market, build_signal_message
from x_fetcher import fetch_latest_posts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ea-bot")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
BOT_USERNAME   = os.environ.get("BOT_USERNAME", "")
PUBLIC_URL     = os.environ["PUBLIC_URL"].rstrip("/")
TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

SUBS_FILE = "subs.json"  # subs armazenadas em disco (persistem entre restarts do Render)

app = FastAPI(title="EA Trader AI – Analyst")

# ---------- helpers ----------
def load_subs() -> List[int]:
    try:
        with open(SUBS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_subs(subs: List[int]) -> None:
    try:
        with open(SUBS_FILE, "w") as f:
            json.dump(subs, f)
    except Exception as e:
        logger.warning(f"Erro a gravar subs: {e}")

async def tg_call(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{TG_API}/{method}"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        async with s.post(url, json=payload) as r:
            data = await r.json()
            if not data.get("ok"):
                logger.warning(f"Telegram API erro: {data}")
            return data

async def send_message(chat_id: int, text: str, parse="Markdown"):
    return await tg_call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": parse})

async def broadcast(text: str):
    subs = load_subs()
    if not subs:
        logger.info("Sem subscritores ainda.")
        return
    await asyncio.gather(*[send_message(cid, text) for cid in subs])

# ---------- startup/shutdown ----------
@app.on_event("startup")
async def on_startup():
    # Define o webhook do Telegram
    webhook_url = f"{PUBLIC_URL}/webhook"
    await tg_call("setWebhook", {"url": webhook_url})
    logger.info(f"Webhook definido para: {webhook_url}")
    # arranca scheduler (job a cada 10 min)
    start_scheduler(lambda: asyncio.create_task(run_cycle()))

@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()

# ---------- ciclo de análise (usado no scheduler) ----------
async def run_cycle():
    """
    1) Vai buscar posts/leaks do X (via Nitter).
    2) Analisa mercado (Futbin + regras).
    3) Se houver oportunidades -> envia alerta para subs.
    """
    try:
        posts = await fetch_latest_posts()
        result = await analyze_market(posts)
        if result and result.get("signals"):
            msg = build_signal_message(result)
            await broadcast(msg)
            logger.info("Sinais enviados.")
        else:
            logger.info("Sem sinais desta vez.")
    except Exception as e:
        logger.exception(f"Erro no ciclo de análise: {e}")

# ---------- rotas FastAPI ----------
@app.get("/")
async def root():
    return {"ok": True, "service": "EA Trader AI – Analyst"}

@app.post("/webhook")
async def telegram_webhook(update: Dict[str, Any]):
    try:
        message = update.get("message") or update.get("edited_message") or {}
        chat_id = message.get("chat", {}).get("id")
        text = (message.get("text") or "").strip()

        if not chat_id or not text:
            return JSONResponse({"ok": True})

        # comandos
        lc = text.lower()
        if lc in ("/start", "start"):
            await send_message(chat_id,
                "👋 Olá! Estou online.\n"
                "Comandos:\n"
                "/help – ajuda\n"
                "/status – estado do bot\n"
                "/subscribe – receber sinais\n"
                "/unsubscribe – parar sinais\n"
                "/signal – exemplo de sinal"
            )
        elif lc in ("/help", "help"):
            await send_message(chat_id,
                "📘 Ajuda:\n"
                "- Eu monitorizo leaks (FutSheriff, etc.), e preços no Futbin.\n"
                "- Se vir oportunidade (subida/queda com % e timing), envio alerta 🚨.\n"
                "- Usa /subscribe para começar a receber os alertas."
            )
        elif lc in ("/status", "status"):
            await send_message(chat_id, get_scheduler_status())
        elif lc in ("/subscribe", "subscribe"):
            subs = load_subs()
            if chat_id not in subs:
                subs.append(chat_id)
                save_subs(subs)
            await send_message(chat_id, "🔔 Subscrito! Vais receber os sinais automáticos.")
        elif lc in ("/unsubscribe", "unsubscribe"):
            subs = load_subs()
            if chat_id in subs:
                subs.remove(chat_id)
                save_subs(subs)
            await send_message(chat_id, "🔕 Subscrição removida.")
        elif lc in ("/signal", "signal"):
            # sinal de exemplo (para teste)
            example = {
                "signals":[
                    {"player":"Example Card 86", "action":"BUY", "price":19000,
                     "reason":"Leak do FutSheriff + volume ↑ + spread baixo",
                     "tp":23000, "sl":17000, "confidence":82}
                ]
            }
            await send_message(chat_id, build_signal_message(example))
        else:
            # eco simples (útil para ver que recebes bem)
            await send_message(chat_id, f"Recebi: {text}")
    except Exception as e:
        logger.exception(f"Erro no webhook: {e}")
    return JSONResponse({"ok": True})        
