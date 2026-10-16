"""PlayStyles and PlayStyle+ for special cards, read from the card's page on FUT.GG.

FIFA Rosters has no PlayStyles, so special cards (TOTW, promos) only knew the base card's,
and promo cards often have one more. FUT.GG's card page shows the card's own PlayStyles:

    https://www.fut.gg/players/<player id>/27-<card id>/

(<card id> is EA's item id, the same id FIFA Rosters calls futid; FUT.GG redirects to the full
address.) FUT.GG's robots.txt forbids /api/, so only the public pages are read: one at a time,
with a pause, and each card once (saved in data/cache/futgg/). Special cards only; base cards
already have PlayStyles from EA.

On the page, the card's PlayStyles are the large icons (height 42) at the top, each in a
<div title="Name">. PlayStyle+ has another icon shape than a plain PlayStyle.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..schema import Player, canonical_playstyle

CARD_URL = "https://www.fut.gg/players/{player}/{game}-{card}/"
_ICON = re.compile(r'<div(?: class="([^"]*)")? title="([^"]+)"><svg[^>]*?height="(\d+)"[^>]*>\s*<path d="([^"]+)"')
_PLAIN = "M128,12.808L243.192,128,128,243.192,12.808,128Z"   # diamond = PlayStyle; other shape = PlayStyle+
_HEIGHT = re.compile(r"Height</[^>]+>\s*<[^>]+>\s*(\d{3})\s*cm", re.I)


class FutggCache:
    def __init__(self, folder: str):
        self.dir = Path(folder)
        self.cards: Dict[str, dict] = {}
        p = self.dir / "kort.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                self.cards = json.load(f)

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "kort.json", "w", encoding="utf-8") as f:
            json.dump(self.cards, f, ensure_ascii=False)


def parse_card_page(html: str) -> Optional[dict]:
    """The card's own PlayStyles: the first unbroken run of large icons. None if the page has none
    (layout changed, or not a card page) so nothing wrong is saved."""
    ps: List[str] = []
    psp: List[str] = []
    started = False
    for m in _ICON.finditer(html):
        cls, name, height, path = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        big = height >= 40 and not cls
        if not big:
            if started:
                break
            continue
        started = True
        canon = canonical_playstyle(name) or name
        (ps if path.startswith(_PLAIN) else psp).append(canon)
    if not started:
        return None
    h = _HEIGHT.search(html)
    return {"ps": [x for x in ps if x not in psp], "psp": psp,
            "height": int(h.group(1)) if h else None,
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%d")}


def fetch_cards(fetcher, cache: FutggCache, cards: Iterable[Tuple[str, str]], limit: int, game: str = "27",
                log=print) -> int:
    """cards: (player id, card id) pairs in the order to fetch. Each card is fetched once.
    A page without PlayStyles is remembered as missing; a network error is tried again next run."""
    import urllib.error
    done, errors = 0, 0
    for player, card in cards:
        card = str(card)
        if done >= limit or errors >= 5:
            if errors >= 5:
                log("  FUT.GG: for mange feil på rad, prøver igjen neste kjøring")
            break
        if not player or not card or card in cache.cards:
            continue
        try:
            rec = parse_card_page(fetcher.get(CARD_URL.format(player=player, game=game, card=card)))
            errors = 0
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                rec = None
            elif exc.code >= 500:  # FUT.GG busy: try this card again next run
                errors += 1
                continue
            else:
                raise
        except (TimeoutError, OSError) as exc:
            errors += 1
            log(f"  FUT.GG: {card} feilet ({exc}), prøver igjen neste gang")
            continue
        cache.cards[card] = rec or {"missing": True, "t": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        done += 1
        if done % 25 == 0:
            log(f"  FUT.GG: {done} kortsider lest")
            cache.save()
    cache.save()
    return done


def load_cards(folder: str) -> Dict[str, dict]:
    p = Path(folder) / "kort.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def apply(players: List[Player], cards: Dict[str, dict]) -> int:
    """Use FUT.GG's PlayStyles (and height where missing) on the cards it has. Returns how many."""
    n = 0
    for p in players:
        rec = cards.get(str(p.id)) if p.id else None
        if not rec or rec.get("missing"):
            continue
        p.playstyles_plus = list(rec.get("psp") or [])
        p.playstyles = [x for x in rec.get("ps") or [] if x not in p.playstyles_plus]
        p.playstyles_complete = True
        p.ps_from_base = False
        if rec.get("height") and not p.height_cm:
            p.height_cm = float(rec["height"])
        n += 1
    return n
