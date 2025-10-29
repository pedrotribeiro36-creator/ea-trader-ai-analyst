# app.py — EA Trader AI (tudo num único ficheiro)
import os, re, time, json, asyncio, requests
from typing import Dict, List, Tuple, Set
from fastapi import FastAPI, Request, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup
import feedparser

# ======================
# CONFIG / ENV VARS
# ======================
TOKEN = os.environ.get("TELEGRAM_TOKEN")  # OBRIGATÓRIA
if not TOKEN:
    raise RuntimeError("Falta a variável de ambiente TELEGRAM_TOKEN!")

API = f"https://api.telegram.org/bot{TOKEN}"
PLATFORM = os.environ.get("PLATFORM", "ps").lower()        # ps | xbox | pc
INTERVAL_MIN = int(os.environ.get("ALERT_INTERVAL_MIN", "10"))

# Fontes RSS (podes editar via ENV: RSS_SOURCES)
DEFAULT_RSS = [
    "https://nitter.net/FutSheriff/rss",
    "https://nitter.net/FUTScoreboard/rss",
    "https://nitter.net/EASPORTSFC/rss",
]
RSS_SOURCES = [
    s.strip() for s in os.environ.get("RSS_SOURCES", ",".join(DEFAULT_RSS)).split(",")
    if s.strip()
]

# ======================
# APP + ESTADO
# ======================
app = FastAPI()
scheduler = AsyncIOScheduler()

SUBS_FILE = "subscribers.json"
SEEN_FILE = "seen.json"
subs: Set[int] = set()
seen_links: Set[str] = set()

def load_state():
    global subs, seen_links
    try:
        subs = set(json.load(open(SUBS_FILE)))
    except Exception:
        subs = set()
    try:
        seen_links = set(json.load(open(SEEN_FILE)))
    except Exception:
        seen_links = set()

def save_state():
    try:
        json.dump(list(subs), open(SUBS_FILE, "w"))
        json.dump(list(seen_links), open(SEEN_FILE, "w"))
    except Exception:
        pass

# ======================
# TELEGRAM HELPERS
# ======================
def tg_send(chat_id: int, text: str, parse: str | None = "HTML", preview: bool = True):
    try:
        requests.post(
            f"{API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse,
                "disable_web_page_preview": preview,
            },
            timeout=20,
        )
    except Exception as e:
        print("tg_send error:", e)

# ======================
# HYPES (RSS do X via Nitter)
# ======================
HYPE_KEYWORDS = [
    r"\bSBC\b", r"\bLeak", r"Upgrade", r"Player\s*Pick", r"Objective",
    r"\bPromo\b", r"\bTOTW\b", r"End of an Era", r"Flash", r"Loan", r"Icon"
]
KW_RE = re.compile("|".join(HYPE_KEYWORDS), re.IGNORECASE)

def classify_hype(text: str) -> str:
    if not text:
        return "low"
    hits = len(KW_RE.findall(text))
    if hits >= 3: return "high"
    if hits == 2: return "medium"
    return "low"

def fetch_rss_items() -> List[dict]:
    items: List[dict] = []
    for url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            src = feed.feed.get("title", url)
            for e in feed.entries[:12]:
                title = e.get("title", "")
                summary = e.get("summary", "")
                link = e.get("link", "")
                pub = e.get("published_parsed") or e.get("updated_parsed")
                ts = time.mktime(pub) if pub else time.time()
                level = classify_hype(f"{title} {summary}")
                items.append({
                    "source": src, "title": title, "summary": summary,
                    "link": link, "published": ts, "level": level
                })
        except Exception as ex:
            print("RSS error:", url, ex)
            continue
    items.sort(key=lambda x: x["published"], reverse=True)
    return items

# ======================
# MERCADO (Futbin - leitura best-effort)
# ======================
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
# Página agregada com preços; serve para fallback robusto
FUTBIN_FODDER = "https://www.futbin.com/stc/prices?bin_platform={platform}"

_market_cache: List[Tuple[float, Dict[int, float]]] = []  # [(ts, {84: price, ...})]

def _get(url: str):
    return requests.get(url, headers=HEADERS, timeout=20)

def _parse_fodder_html(html: str) -> Dict[int, float]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    data: Dict[int, float] = {}
    # Heurística: procurar "84 ... 3,200" etc.
    for rating in (83, 84, 85, 86, 87, 88, 89):
        m = re.search(rf"\b{rating}\b[^0-9]{{1,10}}([0-9][0-9\., ]{{2,}})", text)
        if m:
            val = m.group(1).replace(".", "").replace(",", "").replace(" ", "")
            try:
                data[rating] = float(val)
            except:
                pass
    return data

def fetch_fodder_snapshot(platform: str) -> Dict[int, float]:
    url = FUTBIN_FODDER.format(platform=platform)
    try:
        r = _get(url)
        if r.ok:
            prices = _parse_fodder_html(r.text)
            return prices
    except Exception as e:
        print("Futbin fetch error:", e)
    return {}

def pct(old: float | None, new: float | None) -> float:
    if not old or not new: return 0.0
    try:
        return round((new - old) / old * 100.0, 2)
    except ZeroDivisionError:
        return 0.0

def record_and_variations() -> Tuple[Dict[int, float], Dict[int, float], Dict[int, float]]:
    now = time.time()
    current = fetch_fodder_snapshot(PLATFORM)
    if not current:
        return {}, {}, {}
    _market_cache.append((now, current))
    _market_cache[:] = _market_cache[-200:]  # limita histórico

    def closest(delta_sec: int) -> Dict[int, float]:
        target = now - delta_sec
        best = None
        for ts, snap in _market_cache:
            if best is None or abs(ts - target) < abs(best[0] - target):
                best = (ts, snap)
        return best[1] if best else {}

    ch1, ch24 = {}, {}
    snap1 = closest(60*60)
    snap24 = closest(24*60*60)
    for r, p in current.items():
        ch1[r] = pct(snap1.get(r), p) if snap1 else 0.0
        ch24[r] = pct(snap24.get(r), p) if snap24 else 0.0
    return current, ch1, ch24

def ascii_spark(series: List[float], width: int = 20) -> str:
    series = [s for s in series if s is not None]
    if not series: return ""
    lo, hi = min(series), max(series)
    if hi == lo: return "-"*width
    step = (hi - lo) / width
    out = []
    for x in series:
        pos = int((x - lo) / step) if step else 0
        pos = max(0, min(width-1, pos))
        out.append("|" if pos == width-1 else "_")
    return "".join(out)

# ======================
# SCAN + ALERTA
# ======================
def format_market_block(cur: Dict[int, float], ch1: Dict[int, float], ch24: Dict[int, float]) -> str:
    def line(r):
        v = cur.get(r)
        if v is None: return f"{r}: —"
        return f"{r}: {int(v):,}  (1h {ch1.get(r,0):+.1f}%, 24h {ch24.get(r,0):+.1f}%)".replace(",", ".")
    if not cur: return ""
    # mini tendência com últimos 84s
    series84 = [snap.get(84) for _, snap in _market_cache][-20:]
    trend = ascii_spark(series84, width=20) if len(series84) >= 5 else ""
    block = (
        f"📊 <b>Fodders ({PLATFORM.upper()})</b>\n"
        f"{line(83)}\n{line(84)}\n{line(85)}\n"
    )
    if trend:
        block += f"84 trend: <code>{trend}</code>\n"
    return block

def build_action_hint(item_level: str) -> str:
    lvl = item_level.lower()
    if lvl == "high":
        return "💡 <i>Ação:</i> Se for SBC grande/Upgrade → foco 84–86. Comprar fundo e vender no pico das 1–6h."
    if lvl == "medium":
        return "💡 <i>Nota:</i> Pode aquecer fodder 83–85. Snipes abaixo da média e flips rápidos."
    return "💡 <i>Observação:</i> Monitorizar. Só entrar com margem segura."

def run_scan() -> List[str]:
    out: List[str] = []
    # 1) Hypes
    items = fetch_rss_items()
    new_items = [i for i in items if i["link"] and i["link"] not in seen_links]
    for i in new_items:
        seen_links.add(i["link"])
    if new_items:
        save_state()

    # 2) Mercado
    cur, ch1, ch24 = record_and_variations()
    market_block = format_market_block(cur, ch1, ch24)

    # 3) Mensagens
    if not new_items and not cur:
        return ["Sem sinais fortes agora. A monitorizar…"]

    for it in new_items or []:
        txt = (
            f"🚨 <b>HYPE DETECTADO</b> [{it['level'].upper()}]\n"
            f"Fonte: {it['source']}\n"
            f"Título: {it['title']}\n"
            f"Resumo: {it['summary'][:300]}\n"
            f"🔗 {it['link']}\n\n"
            f"{market_block}"
            f"{build_action_hint(it['level'])}"
        )
        out.append(txt)

    # Se só houver mercado (sem hype novo)
    if not new_items and cur:
        out.append("📊 Atualização de mercado:\n" + market_block)

    return out

# ======================
# WEBHOOK + JOB
# ======================
@app.on_event("startup")
async def startup():
    load_state()
    # agenda job periódico
    scheduler.add_job(hype_job, "interval", minutes=INTERVAL_MIN, next_run_time=None, id="hype_job")
    scheduler.start()

@app.get("/")
async def root():
    return {"ok": True, "service": "EA Trader AI – Analyst", "interval_min": INTERVAL_MIN}

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    # valida token no caminho (robusto a trocas de token)
    if token != TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")

    update = await request.json()
    message = update.get("message") or update.get("edited_message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return {"ok": True}

    if text == "/start":
        tg_send(chat_id,
                "👋 Olá! Estou online.\n"
                "Comandos:\n"
                "/subscribe – começar a receber alertas\n"
                "/unsubscribe – parar alertas\n"
                "/status – ver estado\n"
                "/signal – análise já")
    elif text == "/help":
        tg_send(chat_id,
                "📋 Comandos:\n"
                "/subscribe\n/unsubscribe\n/status\n/signal")
    elif text == "/subscribe":
        subs.add(int(chat_id)); save_state()
        tg_send(chat_id, "🔔 Subscrito! Vais receber TODOS os hypes + análise de mercado.")
    elif text == "/unsubscribe":
        subs.discard(int(chat_id)); save_state()
        tg_send(chat_id, "🔕 Subscrição removida.")
    elif text == "/status":
        tg_send(chat_id, f"✅ Online\nSubscritores: {len(subs)}\nIntervalo: {INTERVAL_MIN} min\nPlataforma: {PLATFORM.upper()}")
    elif text == "/signal":
        tg_send(chat_id, "🔎 A analisar…")
        msgs = run_scan()
        for m in msgs:
            tg_send(chat_id, m)
            time.sleep(0.3)
    else:
        tg_send(chat_id, f"Recebi: {text}")

    return {"ok": True}

async def hype_job():
    if not subs:
        return
    msgs = run_scan()
    for chat_id in list(subs):
        for m in msgs:
            tg_send(chat_id, m)
            await asyncio.sleep(0.2)
