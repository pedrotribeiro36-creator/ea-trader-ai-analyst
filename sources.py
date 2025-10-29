import os, time, re
import feedparser
from dataclasses import dataclass
from typing import List, Dict

HYPE_KEYWORDS = [
    r"\bSBC\b", r"\bLeak", r"Upgrade", r"Player\s*Pick", r"Objective",
    r"\bPromo\b", r"\bTOTW\b", r"End of an Era", r"Flash", r"Loan", r"Icon"
]
KW_RE = re.compile("|".join(HYPE_KEYWORDS), re.IGNORECASE)

@dataclass
class HypeItem:
    source: str
    title: str
    summary: str
    link: str
    published: float
    level: str  # 'low' | 'medium' | 'high'

def classify(text: str) -> str:
    """Classifica o hype por palavras-chave simples."""
    if not text:
        return "low"
    hits = len(KW_RE.findall(text))
    if hits >= 3: return "high"
    if hits == 2: return "medium"
    return "low"

def fetch_rss() -> List[HypeItem]:
    urls = os.environ.get("RSS_SOURCES", "").split(",")
    out: List[HypeItem] = []
    for url in [u.strip() for u in urls if u.strip()]:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                text = f"{e.get('title','')} {e.get('summary','')}"
                level = classify(text)
                pub = e.get("published_parsed") or e.get("updated_parsed")
                ts = time.mktime(pub) if pub else time.time()
                out.append(HypeItem(
                    source=feed.feed.get("title", url),
                    title=e.get("title",""),
                    summary=e.get("summary",""),
                    link=e.get("link",""),
                    published=ts,
                    level=level
                ))
        except Exception:
            continue
    # recentes primeiro
    out.sort(key=lambda x: x.published, reverse=True)
    return out
