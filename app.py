import os
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

# ─────────────────────────────────────────────────────────────
# ▶️ Variáveis de ambiente (obrigações e opcionais)
# ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # obrigatório
PUBLIC_URL      = os.environ.get("PUBLIC_URL")     # recomendado (https://…onrender.com)
FREQ_MINUTES    = int(os.environ.get("FREQ_MINUTES", "10"))  # frequência do scheduler
ADMIN_ID        = os.environ.get("ADMIN_ID")  # opcional: chat id teu para logs
# Conectores opcionais (se não tiver, o conector fica “mute”)
X_BEARER_TOKEN  = os.environ.get("X_BEARER_TOKEN")      # API oficial do X
IG_APP_TOKEN    = os.environ.get("IG_APP_TOKEN")        # Instagram Graph API

if not TELEGRAM_TOKEN:
    raise RuntimeError("Falta TELEGRAM_TOKEN nas variáveis de ambiente do Render.")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
SUBS_FILE = "subs.json"  # persistência simples (reinicio pode limpar em Render free)

app = FastAPI(title="EA Trader AI – Analyst (one-file)")

# ─────────────────────────────────────────────────────────────
# 🗄️ Subs (persistência simples)
# ─────────────────────────────────────────────────────────────
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
    except Exception:
        pass

SUBSCRIBERS: List[int] = load_subs()

# ─────────────────────────────────────────────────────────────
# 📤 Telegram helpers
# ─────────────────────────────────────────────────────────────
async def tg(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{TELEGRAM_API}/{method}", json=payload)
        return r.json()

async def send_msg(chat_id: int, text: str, preview: bool=False):
    await tg("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": not preview,
        "parse_mode": "HTML",
    })

async def broadcast(text: str):
    for cid in list(SUBSCRIBERS):
        try:
            await send_msg(cid, text)
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────
# 🌐 Webhook
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=PlainTextResponse)
def root():
    return "EA Trader AI – Analyst ok"

@app.post("/webhook")
async def webhook(req: Request):
    update = await req.json()
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if text.lower() in ("/start", "start"):
        await send_msg(chat_id, "👋 Olá! O bot está online.\nEscreve /help para ver opções.")
        return {"ok": True}

    if text.lower() in ("/help", "help"):
        await send_msg(chat_id,
            "Comandos:\n"
            "/status – estado do scheduler\n"
            "/subscribe – receber sinais\n"
            "/unsubscribe – parar sinais\n"
            "/signal – forçar análise agora")
        return {"ok": True}

    if text.lower() in ("/subscribe", "subscribe"):
        if chat_id not in SUBSCRIBERS:
            SUBSCRIBERS.append(chat_id)
            save_subs(SUBSCRIBERS)
        await send_msg(chat_id, "✅ Subscreveste os sinais.")
        return {"ok": True}

    if text.lower() in ("/unsubscribe", "unsubscribe"):
        if chat_id in SUBSCRIBERS:
            SUBSCRIBERS.remove(chat_id)
            save_subs(SUBSCRIBERS)
        await send_msg(chat_id, "🚫 Cancelaste a subscrição.")
        return {"ok": True}

    if text.lower() in ("/status", "status"):
        nxt = _next_run_str()
        await send_msg(chat_id, f"🟢 Scheduler ativo.\nPróxima análise: {nxt}\nFrequência: {FREQ_MINUTES} min")
        return {"ok": True}

    if text.lower() in ("/signal", "signal"):
        await send_msg(chat_id, "⏳ A analisar…")
        signals = await analyze_market()
        if signals:
            for s in signals:
                await send_msg(chat_id, s, preview=True)
        else:
            await send_msg(chat_id, "⚪ Sem oportunidades neste momento.")
        return {"ok": True}

    # eco simples (para debug)
    await send_msg(chat_id, f"Recebi: {text}")
    return {"ok": True}

# ─────────────────────────────────────────────────────────────
# 🔗 Auto-set do webhook ao arrancar (se PUBLIC_URL existir)
# ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    if PUBLIC_URL:
        try:
            await tg("setWebhook", {"url": f"{PUBLIC_URL}/webhook"})
        except Exception:
            pass
    # arranca o scheduler loop
    asyncio.create_task(_scheduler_loop())

# ─────────────────────────────────────────────────────────────
# ⏱️ Scheduler “lite” (loop asyncio)
# ─────────────────────────────────────────────────────────────
_next_run: Optional[datetime] = None

def _next_run_str() -> str:
    global _next_run
    if not _next_run:
        return "N/D"
    return _next_run.strftime("%H:%M")

async def _scheduler_loop():
    global _next_run
    # dá 5s para o Render “assentar”
    await asyncio.sleep(5)
    while True:
        try:
            # marca próxima corrida
            _next_run = datetime.utcnow() + timedelta(minutes=FREQ_MINUTES)
            # espera até lá
            await asyncio.sleep(FREQ_MINUTES * 60)

            # corre análise
            signals = await analyze_market()
            if signals:
                header = f"📈 Sinais ({datetime.utcnow().strftime('%H:%M')} UTC):"
                await broadcast(header)
                for s in signals:
                    await broadcast(s)
        except Exception as e:
            if ADMIN_ID:
                try:
                    await send_msg(int(ADMIN_ID), f"⚠️ Erro no scheduler: {e}")
                except Exception:
                    pass
            await asyncio.sleep(5)  # backoff curto

# ─────────────────────────────────────────────────────────────
# 🧠 Análise de mercado (plug-and-play)
# ─────────────────────────────────────────────────────────────
async def analyze_market() -> List[str]:
    """
    Agrega dados de múltiplas fontes.
    - Se X/IG tokens existirem, usa conectores.
    - Caso contrário, usa stubs/dados públicos simples.
    Retorna lista de mensagens formatadas para envio no Telegram.
    """
    candidates: List[Dict[str, Any]] = []

    # 1) Conector X (opcional)
    if X_BEARER_TOKEN:
        tw = await fetch_x_signals(["FutSheriff", "Fut_scoreboard", "Fut_Camp"], minutes=30)
        candidates.extend(tw)

    # 2) Conector Instagram (opcional)
    if IG_APP_TOKEN:
        ig = await fetch_ig_posts(["fut_scoreboard"], minutes=30)
        candidates.extend(ig)

    # 3) Futbin / Fut.gg (placeholder)
    fb = await fetch_futbin_topmovers()
    candidates.extend(fb)

    # 4) Regras simples (exemplo) → transforma em mensagens
    signals: List[str] = []
    for c in candidates:
        # regra de exemplo: variação >= 8% nas últimas 1–3h
        pct = c.get("change_pct", 0)
        if pct >= 8:
            name = c.get("name", "Ativo")
            price = c.get("price", "?")
            src = c.get("src", "mercado")
            url = c.get("url", "")
            msg = (
                f"<b>🟢 Oportunidade</b>\n"
                f"{name} subiu <b>{pct:.1f}%</b> • Preço: {price}\n"
                f"Fonte: {src}\n"
                f"{url}"
            )
            signals.append(msg)

    # se não houver nada, mas queres validar, envia demo 1x/dia
    return signals

# ─────────────────────────────────────────────────────────────
# 🔌 Conectores (mínimos/placeholder)
# ─────────────────────────────────────────────────────────────
async def fetch_x_signals(handles: List[str], minutes: int=30) -> List[Dict[str, Any]]:
    """
    Precisa de X_BEARER_TOKEN válido (API oficial). Se não houver, retorna [].
    Implementação simplificada: devolve estrutura compatível com a “regra”.
    """
    if not X_BEARER_TOKEN:
        return []
    # Exemplo mínimo (não chama endpoints reais aqui por simplicidade)
    # Podes implementar GET search/recent com query "from:handle (palavras-chave)"
    return []  # implementar se forneceres o token oficial

async def fetch_ig_posts(accounts: List[str], minutes: int=30) -> List[Dict[str, Any]]:
    if not IG_APP_TOKEN:
        return []
    return []  # implementar se forneceres o token oficial

async def fetch_futbin_topmovers() -> List[Dict[str, Any]]:
    """
    Placeholder: sem API pública; scraping pode violar ToS.
    Aqui devolvemos um “exemplo” fictício para validar o fluxo.
    Substitui por uma API tua/planilha/webhook próprio quando quiseres.
    """
    # Exemplo “mock” (para veres o bot a enviar algo quando houver variação >= 8%)
    demo = [
        {"name": "FUT Card XYZ", "price": "18,250", "change_pct": 9.4, "src": "Futbin (mock)", "url": "https://www.futbin.com/"},
        {"name": "FUT Card ABC", "price": "22,000", "change_pct": 3.1, "src": "Futbin (mock)", "url": "https://www.futbin.com/"},
    ]
    return demo
