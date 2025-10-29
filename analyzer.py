import re, requests, feedparser
from bs4 import BeautifulSoup

HEADERS = {"User-Agent":"Mozilla/5.0"}
URL_CHEAP_BY_RATING = "https://www.futbin.com/players?version=all&sort=PricePS"
URL_SBC_LATEST = "https://www.futbin.com/squad-building-challenges"
NITTER_RSS = "https://nitter.net/FutSheriff/rss"
KEYWORDS_LEAK = re.compile(r"(sbc|upgrade|repeatable|player pick|party bag|totw|leak|objective|flash|daily|evolutions?)", re.I)

def _get(url, timeout=15):
    return requests.get(url, headers=HEADERS, timeout=timeout)

def _parse_price(txt):
    import re
    try: return int(re.sub(r"[^\d]","", txt))
    except: return None

def scan_futbin():
    signals=[]
    try:
        r=_get(URL_CHEAP_BY_RATING)
        soup=BeautifulSoup(r.text,"lxml")
        rows=soup.select("table tr")
        cheap=[]
        for tr in rows[:300]:
            txt=tr.get_text(" ", strip=True)
            m_ovr=re.search(r"\b(8[2-5])\b", txt)  # 82–85
            m_price=re.search(r"(\d[\d,\.]{2,})", txt)
            if m_ovr and m_price:
                ovr=int(m_ovr.group(1))
                price=_parse_price(m_price.group(1))
                if price and 300<price<6000:
                    cheap.append((ovr,price))
        bucket={}
        for ovr,price in cheap:
            bucket.setdefault(ovr,[]).append(price)
        for ovr in (82,83,84,85):
            arr=bucket.get(ovr,[])
            if len(arr)>=5:
                avg=sum(arr)/len(arr)
                if ovr>=84 and avg>=3500:
                    signals.append({"type":"FODDER","msg":f"Fodder {ovr} a subir (média ~{int(avg):,}). Comprar < {int(avg*0.9):,} | Vender ~ {int(avg*1.12):,}","confidence":"média"})
                elif ovr==83 and avg>=1500:
                    signals.append({"type":"FODDER","msg":f"Fodder 83 a aquecer (média ~{int(avg):,}). Snipes < {int(avg*0.9):,} | Flip ~ {int(avg*1.15):,}","confidence":"média"})
    except Exception as e:
        signals.append({"type":"INFO","msg":f"[Futbin] erro: {e}","confidence":"baixa"})
    try:
        r=_get(URL_SBC_LATEST)
        soup=BeautifulSoup(r.text,"lxml")
        cards=[c.get_text(" ",strip=True) for c in soup.select(".players_list .player_name, .players_list .sub_header")]
        hot=[c for c in cards[:25] if re.search(r"(SBC|Upgrade|Loan|Pick|Pack|TOTW|Icon)", c, re.I)]
        if hot:
            signals.append({"type":"SBC","msg":"SBCs recentes: "+"; ".join(hot[:5]),"confidence":"média"})
    except Exception as e:
        signals.append({"type":"INFO","msg":f"[Futbin SBC] erro: {e}","confidence":"baixa"})
    return signals

def scan_futsheriff():
    signals=[]
    try:
        feed=feedparser.parse(NITTER_RSS)
        for e in feed.entries[:10]:
            title=e.get("title","")
            if KEYWORDS_LEAK.search(title):
                link=e.get("link","")
                signals.append({"type":"LEAK","msg":f"Leak: {title}\n{link}","confidence":"alta"})
    except Exception as e:
        signals.append({"type":"INFO","msg":f"[FutSheriff] erro: {e}","confidence":"baixa"})
    return signals

def run_scan():
    out=[]
    for s in (scan_futbin()+scan_futsheriff()):
        out.append(f"【{s.get('type','INFO')} | conf. {s.get('confidence','-')}】 {s['msg']}")
    return out or ["Sem sinais fortes agora. A monitorizar…"]
