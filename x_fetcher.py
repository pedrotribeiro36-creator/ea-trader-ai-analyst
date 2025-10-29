# x_fetcher.py
import asyncio, aiohttp, re
from bs4 import BeautifulSoup

# Páginas Nitter (mirrors públicos do X/Twitter)
NITTER_BASES = [
    "https://nitter.net",          # principal
    "https://nitter.net",          # redundância (mantém igual; podes adicionar outros mirrors)
]

# Contas mais usadas pela comunidade de FUT (podes acrescentar)
ACCOUNTS = [
    "FutSheriff", "Fut_scoreboard", "FUTZONEFIFA", "fifa_romania", "EASPORTSFC",
]

async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, headers={"User-Agent":"Mozilla/5.0"}) as r:
        return await r.text()

def _parse_nitter(html: str):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for art in soup.select("div.timeline-item"):
        text = art.select_one(".tweet-content")
        if not text: 
            continue
        content = text.get_text(" ", strip=True)
        # heurística simples: só leaks/hype aparentes
        if any(k in content.lower() for k in ["leak", "incoming", "today", "mini release", "sbc", "objective", "promo"]):
            items.append(content[:400])
    return items

async def fetch_latest_posts():
    results = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
        for base in NITTER_BASES:
            for acc in ACCOUNTS:
                url = f"{base}/{acc}"
                try:
                    html = await _fetch_html(s, url)
                    results.extend(_parse_nitter(html))
                    await asyncio.sleep(0.7)  # respeitar rate
                except Exception:
                    pass
    # remove duplicados
    dedup = []
    seen = set()
    for t in results:
        k = t.lower()
        if k not in seen:
            seen.add(k); dedup.append(t)
    return dedup
