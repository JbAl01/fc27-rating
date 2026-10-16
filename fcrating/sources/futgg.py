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
# Roles: the page data has a score per role the card can play, with its familiarity (isPlus / isPlusPlus).
# Roles are numbers there (the names are only in a script that robots.txt closes); which position each number
# belongs to is in config/sources.json (specials.futgg.role_positions).
_SCORES = re.compile(r'role:(\d+),chemistryStyle:1,score:[\d.]+,rank:\d+,isPlus:!([01]),isPlusPlus:!([01])')
_RP = re.compile(r'rolesPlus:\$R\[\d+\]=\[([\d,]*)\],rolesPlusPlus:\$R\[\d+\]=\[([\d,]*)\]')
_POS = re.compile(r'position:(\d+),alternativePositionIds:\$R\[\d+\]=\[([\d,]*)\]')
_ICON = re.compile(r'<div(?: class="([^"]*)")? title="([^"]+)"><svg[^>]*?height="(\d+)"[^>]*>\s*<path d="([^"]+)"')
_PLAIN = "M128,12.808L243.192,128,128,243.192,12.808,128Z"   # diamond = PlayStyle; other shape = PlayStyle+
_HEIGHT = re.compile(r"Height</[^>]+>\s*<[^>]+>\s*(\d{3})\s*cm", re.I)


_FR_PLAYER = re.compile(r"[?&]player=(\d+)")


def player_page(p: Player, game: str = "27") -> Optional[str]:
    """The card's public page on FUT.GG: /players/<player id>/27-<card id>/. The player id is the base card's id
    (special cards), the player id in the FIFA Rosters address (Icons and Heroes have no base card here), or the
    card's own id (base cards, where card and player id are the same). None for cards without a known id."""
    card = str(p.id or "").strip()
    if not card.isdigit():
        return None
    player = str(p.base_id or "").strip()
    if not player.isdigit():
        m = _FR_PLAYER.search(p.url or "")
        player = m.group(1) if m else card
    return CARD_URL.format(player=player, game=game, card=card)


def load_role_positions() -> Dict[str, List[int]]:
    """config/sources.json: specials.futgg.role_positions."""
    p = Path(__file__).resolve().parent.parent.parent / "config" / "sources.json"
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("specials", {}).get("futgg") or {}).get("role_positions") or {}
    except (OSError, ValueError):
        return {}


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


def parse_roles(html: str) -> Optional[dict]:
    """{"r": {role number: 0/1/2}, "p": [ids with +], "pp": [ids with ++], "pos": EA position id} for the card
    on the page (its own data comes first). None if the page has no role data."""
    i = html.find("scores:$R[")
    roles: Dict[str, int] = {}
    if i >= 0:
        for m in _SCORES.finditer(html, i, i + 20000):
            roles.setdefault(m.group(1), 2 if m.group(3) == "0" else 1 if m.group(2) == "0" else 0)
    rp, pos = _RP.search(html), _POS.search(html)
    if not roles and not rp:
        return None
    ids = lambda t: [int(x) for x in t.split(",") if x]
    return {"r": roles, "p": ids(rp.group(1)) if rp else [], "pp": ids(rp.group(2)) if rp else [],
            "pos": int(pos.group(1)) if pos else None}


def parse_card_page(html: str) -> Optional[dict]:
    """The card's own PlayStyles: the first unbroken run of large icons, and its roles. None if the page has
    neither (layout changed, or not a card page) so nothing wrong is saved."""
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
    roles = parse_roles(html)
    if not started and not roles:
        return None
    h = _HEIGHT.search(html)
    rec = {"ps": [x for x in ps if x not in psp], "psp": psp,
           "height": int(h.group(1)) if h else None,
           "t": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    if not started:
        rec["no_ps"] = True   # the icons were not found: keep the card's own PlayStyles
    if roles:
        rec["roles"] = roles
    return rec


def fetch_cards(fetcher, cache: FutggCache, cards: Iterable[Tuple[str, str]], limit: int, game: str = "27",
                log=print, kind: Optional[str] = None) -> int:
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
        rec = rec or {"missing": True, "t": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        if kind:
            rec["kind"] = kind
        cache.cards[card] = rec
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


EA_POSITIONS = {0: "GK", 2: "RWB", 3: "RB", 5: "CB", 7: "LB", 8: "LWB", 10: "CDM", 12: "RM", 14: "CM", 16: "LM",
                18: "CAM", 21: "CF", 23: "RW", 25: "ST", 27: "LW"}


def roles_from(rec: dict, role_positions: Dict[str, List[int]], position: str) -> Optional[Dict[str, Dict[str, int]]]:
    """The card's familiarity per position, {"ST": {"": 2}}: the best role in each position it can play
    (that is what IGR uses). Keepers have no role scores on the page, only the + and ++ lists."""
    r = rec.get("roles")
    if not r:
        return None
    pos_of = {str(i): pos for pos, ids in role_positions.items() if not str(pos).startswith("_") for i in ids}
    out: Dict[str, Dict[str, int]] = {}
    for rid, lv in r.get("r", {}).items():
        pos = pos_of.get(str(rid))
        if pos:
            out[pos] = {"": max(lv, out.get(pos, {}).get("", 0))}
    if (position or "").upper() == "GK" or EA_POSITIONS.get(r.get("pos")) == "GK":
        out["GK"] = {"": 2 if r.get("pp") else 1 if r.get("p") else 0}
    return out or None


def apply(players: List[Player], cards: Dict[str, dict], role_positions: Optional[Dict[str, List[int]]] = None) -> int:
    """Use FUT.GG's PlayStyles (and height where missing) on the cards it has. Returns how many.
    Base cards (fetched for their roles) keep EA's PlayStyles and get their real roles (+ and ++);
    special cards keep ++ in every role (EA's rule for special items)."""
    n = 0
    for p in players:
        rec = cards.get(str(p.id)) if p.id else None
        if not rec or rec.get("missing"):
            continue
        if rec.get("kind") == "base":
            roles = roles_from(rec, role_positions or {}, p.position)
            if roles:
                p.roles, p.roles_complete = roles, True
        elif not rec.get("no_ps"):
            p.playstyles_plus = list(rec.get("psp") or [])
            p.playstyles = [x for x in rec.get("ps") or [] if x not in p.playstyles_plus]
            p.playstyles_complete = True
            p.ps_from_base = False
        if rec.get("height") and not p.height_cm:
            p.height_cm = float(rec["height"])
        n += 1
    return n
