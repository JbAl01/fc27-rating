"""RealSport101: leaked FC 27 cards before they are released.

Their weekly "Team of the Week N Leaked" articles have a table with player,
OVR, PlayStyle+ and all six face stats. Articles that only list names (some
promo leaks) give no stats and are skipped. Leaked cards are built from the
EA base card and marked "lekket" until FIFA Rosters has the released card.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

from ..htmltext import extract
from ..schema import canonical_playstyle

SITE = "https://realsport101.com/"
_RELEVANT = re.compile(r"(team of the week|totw|leak|leaked|team \d+|squad|promo|icons?|heroes?)", re.I)
_STATS = re.compile(
    r"(\d{1,2})\s*pace,?\s*(\d{1,2})\s*shooting,?\s*(\d{1,2})\s*passing,?\s*(\d{1,2})\s*dribbling,?\s*"
    r"(\d{1,2})\s*defending,?\s*(\d{1,2})\s*physical", re.I)
_VERSION = re.compile(r"(Team of the Week \d+|TOTW \d+|[A-Z][A-Za-z']+(?: (?:[A-Z][A-Za-z']+|for|of|the|and))* Team \d+)")


def article_links(html: str) -> List[Dict[str, str]]:
    """FC 27 card articles from the EA Sports FC category page."""
    _, links, _ = extract(html)
    out, seen = [], set()
    for href, text in links:
        url = urljoin(SITE, href)
        if "/article/" not in url or "fc-27" not in url or url in seen:
            continue
        if _RELEVANT.search(text) or _RELEVANT.search(url.replace("-", " ")):
            seen.add(url)
            out.append({"url": url, "title": text})
    return out


def version_from_title(title: str) -> str:
    m = _VERSION.search(title or "")
    return m.group(1) if m else "Lekkasje"


def parse_article(html: str, title: str = "") -> List[dict]:
    """Return cards with name, ovr, ps_plus and face stats."""
    text, _, tables = extract(html)
    if not title:
        first = text.split("\n", 1)[0]
        title = first
    version = version_from_title(title)
    cards: List[dict] = []

    def add(name: str, ovr: str, ps: str, stats_text: str) -> None:
        m = _STATS.search(stats_text)
        if not m or not re.fullmatch(r"\d{2}", ovr.strip()):
            return
        face = dict(zip(["pac", "sho", "pas", "dri", "def", "phy"], map(float, m.groups())))
        ps_name = canonical_playstyle(ps.strip()) if ps and ps.strip() else None
        cards.append({"name": name.strip(), "ovr": int(ovr), "ps_plus": [ps_name] if ps_name else [],
                      "face": face, "version": version})

    for table in tables:
        if not table:
            continue
        header = [c.lower() for c in table[0]]
        has_header = any("player" in c for c in header)
        rows = table[1:] if has_header else table
        idx = {
            "name": next((i for i, c in enumerate(header) if "player" in c or "name" in c), 0),
            "ovr": next((i for i, c in enumerate(header) if c in ("ovr", "rating", "overall")), 1),
            "ps": next((i for i, c in enumerate(header) if "ps" in c or "playstyle" in c), None),
        }
        for row in rows:
            joined = " | ".join(row)
            if not _STATS.search(joined) or len(row) <= max(idx["name"], idx["ovr"]):
                continue
            ps = row[idx["ps"]] if idx["ps"] is not None and idx["ps"] < len(row) else ""
            add(row[idx["name"]], row[idx["ovr"]], ps, joined)

    if not cards:  # no html table: try "Name | 90 | Rapid | 92 pace, ..." lines
        for line in text.split("\n"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3 and _STATS.search(line):
                ps = parts[2] if not _STATS.search(parts[2]) else ""
                add(parts[0], parts[1], ps, line)
    return cards


class LeakCache:
    def __init__(self, folder: str):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.file = self.folder / "lekkasjer.json"
        self.articles: Dict[str, dict] = {}
        if self.file.exists():
            with open(self.file, encoding="utf-8") as f:
                self.articles = json.load(f)

    def save(self) -> None:
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.articles, f, ensure_ascii=False)

    def all_cards(self) -> List[dict]:
        out = []
        for url, art in self.articles.items():
            for c in art.get("cards", []):
                out.append(dict(c, url=url))
        return out


def fetch_leaks(fetcher, cache: LeakCache, category_url: str, pages: int = 1,
                refetch_recent: int = 3, log=print) -> int:
    """Read the category page(s) and parse new articles. The newest few are
    re-read each time, because leak articles get updated."""
    links: List[Dict[str, str]] = []
    for page in range(1, pages + 1):
        url = category_url if page == 1 else category_url.rstrip("/") + f"/page/{page}"
        links.extend(article_links(fetcher.get(url)))
    new = 0
    for i, link in enumerate(links):
        if link["url"] in cache.articles and i >= refetch_recent:
            continue
        cards = parse_article(fetcher.get(link["url"]), link["title"])
        cache.articles[link["url"]] = {"title": link["title"], "cards": cards}
        new += len(cards)
    cache.save()
    log(f"  RealSport101: {len(links)} artikler sjekket, {new} kort med tall")
    if not links:
        log("  Fant ingen FC 27-artikler. Har RealSport101 endret oppsett? Se README.")
    return new
