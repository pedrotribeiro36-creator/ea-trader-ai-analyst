# market_analyzer.py
import asyncio, random, statistics, time
import requests
from bs4 import BeautifulSoup

USER_AGENT = {"User-Agent":"Mozilla/5.0"}

# Exemplos de endpoints do Futbin (ajusta conforme necessidade)
FUTBIN_BASE = "https://www.futbin.com"
SAMPLE_PLAYERS = [
    # (id, nome), ids são os da base do Futbin – podes substituir pelos teus alvos
    ("235988","Vinícius Jr."),
    ("247635","Bukayo Saka"),
    ("230621","Erling Haaland"),
]

def fetch_player_price(player_id: str) -> int | None:
    """
    Tenta obter o preço atual do jogador no Futbin (web).
    Nota: Futbin pode limitar. Mantemos heurísticas/fallback.
    """
    try:
        url = f"{FUTBIN_BASE}/23/player/{player_id}"
        r = requests.get(url, headers=USER_AGENT, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        # procura algo que pareça preço, fallback simples
        el = soup.select_one(".price")
        if el:
            txt = el.get_text().replace(",","").strip()
            num = int("".join(ch for ch in txt if ch.isdigit()))
            return num if num>0 else None
    except Exception:
        return None
    return None

async def analyze_market(posts: list[str]) -> dict:
    """
    Mistura sinais do X com variações de preço de alguns jogadores.
    Regra simples (exemplo): se houver leak/hype + preço atual < média N dias => BUY
    """
    # 1) obter preços (com timeouts)
    prices = []
    for pid, name in SAMPLE_PLAYERS:
        p = fetch_player_price(pid)
        if p:
            prices.append((name, p))
        await asyncio.sleep(0.6)

    # 2) fallback se Futbin recusar requests
    if not prices:
        # cria dados sintéticos para não ficar vazio (remove isto quando tiveres endpoints próprios)
        prices = [("Vinícius Jr.", random.randint(8000, 24000)),
                  ("Bukayo Saka", random.randint(9000, 20000)),
                  ("Erling Haaland", random.randint(15000, 28000))]

    # 3) heurística de hype via X
    hype = any(any(k in p.lower() for k in ["leak", "sbc", "promo", "incoming", "mini release"]) for p in posts)

    signals = []
    for name, price in prices:
        # simulamos “média histórica” com var aleatória (troca por histórico real se quiseres)
        pseudo_mean = int(price * random.uniform(0.95, 1.10))
        delta = price - pseudo_mean
        pct = round((delta / pseudo_mean) * 100, 2) if pseudo_mean else 0.0

        if hype and price < pseudo_mean * 0.96:
            # BUY
            tp = int(price * 1.18)
            sl = int(price * 0.90)
            signals.append({"player":name, "action":"BUY", "price":price,
                            "reason":"Hype/leak + preço abaixo da média",
                            "tp":tp, "sl":sl, "confidence":min(95, 70 + int(abs(pct)))})
        elif (not hype) and price > pseudo_mean * 1.07:
            # SELL
            tp = int(price * 0.92)
            sl = int(price * 1.10)
            signals.append({"player":name, "action":"SELL", "price":price,
                            "reason":"Sem hype + preço acima da média",
                            "tp":tp, "sl":sl, "confidence":min(93, 65 + int(abs(pct)))})

    return {"hype": hype, "prices": prices, "signals": signals}

def build_signal_message(result: dict) -> str:
    hype = "Sim" if result.get("hype") else "Não"
    lines = [f"*EA Trader AI – Sinais*", f"_Hype X/Nitter_: *{hype}*", ""]
    sigs = result.get("signals") or []
    if not sigs:
        lines.append("Sem oportunidades claras agora.")
    else:
        for s in sigs:
            lines.append(
                f"• *{s['player']}* — *{s['action']}*\n"
                f"  Preço: `{s['price']}` | TP: `{s['tp']}` | SL: `{s['sl']}`\n"
                f"  Motivo: _{s['reason']}_\n"
                f"  Confiança: *{s['confidence']}%*\n"
            )
    return "\n".join(lines)
