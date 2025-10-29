import os, time, json, re, requests
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple

# Guardamos leituras recentes para calcular variações
_cache = {
    "fodder": [],  # [(ts, {83: price, 84: price, 85: price})]
    "players": {}  # name -> [(ts, price)]
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def _get(url: str) -> requests.Response:
    return requests.get(url, headers=HEADERS, timeout=20)

def _parse_fodder_prices_html(html: str) -> Dict[int, float]:
    """
    Faz uma leitura 'best effort' de preços médios por rating a partir da página de preços da Futbin.
    Se a estrutura mudar, continua a correr sem bloquear (retorna vazio).
    """
    soup = BeautifulSoup(html, "html.parser")
    data: Dict[int, float] = {}
    text = soup.get_text(" ", strip=True)

    # Heurística simples: procurar “84 … 3,200” etc.
    for rating in (83, 84, 85, 86, 87, 88, 89):
        m = re.search(rf"\b{rating}\b[^0-9]{1,10}([0-9][0-9\., ]{{2,}})", text)
        if m:
            val = m.group(1).replace(".", "").replace(",", "").replace(" ", "")
            try:
                data[rating] = float(val)
            except:
                pass
    return data

def fetch_fodder_snapshot(platform: str="ps") -> Dict[int, float]:
    """
    Tenta obter preços dos fodders.
    1) tenta endpoints públicos conhecidos
    2) fallback: parse de HTML de listagens
    """
    # Fallback HTML (robusto a mudanças) – página agregada
    url = f"https://www.futbin.com/stc/prices?bin_platform={platform}"
    try:
        r = _get(url)
        if r.ok:
            prices = _parse_fodder_prices_html(r.text)
            if prices:
                return prices
    except Exception:
        pass
    return {}

def pct_change(old: float, new: float) -> float:
    if old is None or old == 0: return 0.0
    return round((new - old) / old * 100.0, 2)

def record_and_compute(platform: str="ps") -> Tuple[Dict[int, float], Dict[int, float], Dict[int, float]]:
    """
    Faz uma leitura, grava no cache e devolve:
    (preço atual, variação vs. 1h, variação vs. 24h) – se existirem amostras.
    """
    now = time.time()
    current = fetch_fodder_snapshot(platform)
    if not current:
        return {}, {}, {}

    _cache["fodder"].append((now, current))
    # manter últimas 200 amostras
    _cache["fodder"] = _cache["fodder"][-200:]

    def closest(delta_sec: int):
        target = now - delta_sec
        # amostra mais próxima do target
        best = None
        for ts, snap in _cache["fodder"]:
            if best is None or abs(ts - target) < abs(best[0] - target):
                best = (ts, snap)
        return best[1] if best else {}

    one_h = closest(60*60)
    one_d = closest(24*60*60)
    ch1, ch24 = {}, {}
    for r, p in current.items():
        ch1[r]  = pct_change(one_h.get(r), p) if one_h else 0.0
        ch24[r] = pct_change(one_d.get(r), p) if one_d else 0.0

    return current, ch1, ch24

def ascii_sparkline(series: List[float], width: int=20) -> str:
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
