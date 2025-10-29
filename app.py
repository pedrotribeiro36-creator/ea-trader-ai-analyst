    import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ---------- Config ----------
SERVICE_NAME = "EA Trader AI – Analyst"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")  # ex.: https://ea-trader-ai-analyst.onrender.com
ANALYZE_EVERY_MIN = int(os.getenv("ANALYZE_EVERY_MIN", "10"))

# Ficheiro para persistir subscritores (persistência simples)
SUBS_FILE = "subscribers.json"

# ---------- Futbin helper (opcional) ----------
try:
    from futbin_client import login_and_check as futbin_login_and_check  # já fornecido antes
except Exception:
    futbin_login_and_check = None  # se o ficheiro ainda não existir

# ---------- App ----------
app = FastAPI(title=SERVICE_NAME, version="1.0.0")
http = httpx.AsyncClient(timeout=30.0)

# ---------- Utilitários de subscrição ----------
def _load_subscribers() -> List[int]:
    try:
        with open(SUBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_subscribers(chat_ids: List[int]) -> None:
    try:
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(chat_ids, f)
    except Exception:
        pass


# ---------- Telegram ----------
def _tg_api(method: str) -> str:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN não configurado.")
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"


async def tg_send_message(chat_id: int, text: str, disable_preview: bool = True):
    url = _tg_api("sendMessage")
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": disable_preview}
    try:
        await http.post(url, json=payload)
    except Exception:
        pass


async def tg_set_webhook() -> Dict[str, Any]:
    if not TELEGRAM_TOKEN or not BASE_URL:
        return {"ok": False, "detail": "Falta TELEGRAM_TOKEN ou BASE_URL"}

    webhook_url = f"{BASE_URL}/webhook/{TELEGRAM_TOKEN}"
    # remove e volta a definir para evitar webhooks antigos
    try:
        await http.get(_tg_api("deleteWebhook"))
    except Exception:
        pass
    r = await http.get(_tg_api("setWebhook"), params={"url": webhook_url})
    try:
        return r.json()
    except Exception:
        return {"ok": False, "detail": f"Resposta inesperada: {r.text[:200]}"}


# ---------- “Análise” (placeholder) ----------
async def fetch_market_snapshot() -> Dict[str, Any]:
    """
    Aqui ficará a tua lógica real de análise (Futbin/X/etc.).
    Por agora é um 'mock' que devolve um resumo com timestamp.
    """
    # TODO: substituir por análise real (scraping APIs próprias/legais)
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": "Mercado está estável; sem desvios > ±2% nas últimas 24h.",
        "top_opportunity": None,
    }


async def analyze_and_broadcast():
    subs = _load_subscribers()
    if not subs:
        return  # ninguém para notificar

    snapshot = await fetch_market_snapshot()
    txt = (
        "📊 *Atualização de Mercado*\n"
        f"⏱ {snapshot['timestamp']}\n"
        f"Resumo: {snapshot['summary']}\n"
        f"Oportunidade: {snapshot['top_opportunity'] or '—'}"
    )
    # envia para todos (silenciosamente ignora erros)
    await asyncio.gather(*(tg_send_message(cid, txt, True) for cid in subs))


# ---------- Scheduler ----------
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler()
JOB_ID = "market_job"


def _start_scheduler():
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    trigger = IntervalTrigger(minutes=max(1, ANALYZE_EVERY_MIN))
    scheduler.add_job(analyze_and_broadcast, trigger=trigger, id=JOB_ID, replace_existing=True)
    if not scheduler.running:
        scheduler.start()


def _next_run_iso() -> Optional[str]:
    job = scheduler.get_job(JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


# ---------- FastAPI rotas ----------
@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/health", tags=["health"])
async def health():
    return {"ok": True}


@app.get("/status", tags=["status"])
async def status():
    return {
        "scheduler_active": scheduler.running,
        "frequency_min": ANALYZE_EVERY_MIN,
        "next_run": _next_run_iso(),
        "subscribers_count": len(_load_subscribers()),
        "webhook_set": bool(TELEGRAM_TOKEN and BASE_URL),
    }


@app.get("/futbin/test", tags=["futbin"])
async def futbin_test():
    if futbin_login_and_check is None:
        raise HTTPException(status_code=500, detail="futbin_client.py não encontrado.")
    user = os.getenv("FUTBIN_USER")
    pw = os.getenv("FUTBIN_PASS")
    if not user or not pw:
        raise HTTPException(status_code=500, detail="FUTBIN_USER/FUTBIN_PASS não definidos.")
    # correr de forma síncrona num thread para não bloquear o loop
    from functools import partial
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, partial(futbin_login_and_check, user, pw))
    # 200 se ok, caso contrário 502 (bad gateway/rede)
    status_code = 200 if result.get("ok") else 502
    return JSONResponse(status_code=status_code, content=result)


# ---------- Telegram webhook ----------
@app.post("/webhook/{token}", tags=["telegram"])
async def tg_webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido.")

    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return {"ok": True}

    # Comandos
    if text.lower() in ("/start", "start"):
        subs = _load_subscribers()
        if chat_id not in subs:
            subs.append(chat_id)
            _save_subscribers(subs)
        await tg_send_message(
            chat_id,
            "👋 Olá! O bot está online.\n"
            "Usa /help para ver opções. Estás subscrito às notificações.",
        )
        return {"ok": True}

    if text.lower() in ("/help", "help"):
        await tg_send_message(
            chat_id,
            "Comandos:\n"
            "/start – ativar e subscrever\n"
            "/help – esta ajuda\n"
            "/status – ver estado do bot\n"
            "/subscribe – receber sinais\n"
            "/unsubscribe – parar sinais\n"
            "/signal – enviar um sinal de teste",
        )
        return {"ok": True}

    if text.lower() in ("/subscribe", "subscribe"):
        subs = _load_subscribers()
        if chat_id not in subs:
            subs.append(chat_id)
            _save_subscribers(subs)
        await tg_send_message(chat_id, "✅ Subscrito. Irás receber atualizações periódicas.")
        return {"ok": True}

    if text.lower() in ("/unsubscribe", "unsubscribe"):
        subs = [cid for cid in _load_subscribers() if cid != chat_id]
        _save_subscribers(subs)
        await tg_send_message(chat_id, "❎ Subscrição cancelada. Podes voltar com /subscribe.")
        return {"ok": True}

    if text.lower() in ("/status", "status"):
        await tg_send_message(
            chat_id,
            f"🟢 Scheduler ativo\n"
            f"Próxima análise: {(_next_run_iso() or 'N/D')}\n"
            f"Frequência: {ANALYZE_EVERY_MIN} min",
        )
        return {"ok": True}

    if text.lower().startswith("/signal"):
        # Sinal manual de teste
        await tg_send_message(chat_id, "📣 Sinal de teste: (apenas um exemplo).")
        return {"ok": True}

    # eco simples para qualquer outro texto
    await tg_send_message(chat_id, f"Recebi: {text}")
    return {"ok": True}


# ---------- Eventos de arranque/fecho ----------
@app.on_event("startup")
async def on_startup():
    # arranca o scheduler
    _start_scheduler()
    # tenta configurar o webhook
    try:
        res = await tg_set_webhook()
        print("Webhook set result:", res)
    except Exception as e:
        print("Falha ao definir webhook:", str(e))


@app.on_event("shutdown")
async def on_shutdown():
    try:
        await http.aclose()
    except Exception:
        pass                    
