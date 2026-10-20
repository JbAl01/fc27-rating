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
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..schema import ATTRIBUTE_LABELS, CARD_IMAGE_HOSTS, Player, canonical_playstyle

CARD_URL = "https://www.fut.gg/players/{player}/{game}-{card}/"
# Roles: the page data has a score per role the card can play, with its familiarity (isPlus / isPlusPlus).
# Roles are numbers there (the names are only in a script that robots.txt closes); which position each number
# belongs to is in config/sources.json (specials.futgg.role_positions).
_SCORES = re.compile(r'role:(\d+),chemistryStyle:1,score:[\d.]+,rank:\d+,isPlus:!([01]),isPlusPlus:!([01])')
_RP = re.compile(r'rolesPlus:\$R\[\d+\]=\[([\d,]*)\],rolesPlusPlus:\$R\[\d+\]=\[([\d,]*)\]')
_POS = re.compile(r'position:(\d+),alternativePositionIds:\$R\[\d+\]=\[([\d,]*)\]')
_ICON = re.compile(r'<div(?: class="([^"]*)")? title="([^"]+)"><svg[^>]*?height="(\d+)"[^>]*>\s*<path d="([^"]+)"')
_PLAIN = "M128,12.808L243.192,128,128,243.192,12.808,128Z"   # diamond = PlayStyle; other shape = PlayStyle+
_SVG = re.compile(r'<div(?: class="([^"]*)")? title="([^"]+)"><svg([^>]*)>(.*?)</svg>', re.S)
_SVG_D = re.compile(r'<path[^>]*?\sd="([MmLlHhVvCcSsQqTtAaZz0-9.,\-\s]{1,20000})"')
_SVG_VB = re.compile(r'viewBox="([\d.\s\-]{3,40})"')
_HEIGHT = re.compile(r"Height</[^>]+>\s*<[^>]+>\s*(\d{3})\s*cm", re.I)
_WEIGHT = re.compile(r"Weight</[^>]+>\s*<[^>]+>\s*(\d{2,3})\s*kg", re.I)
_BODY = re.compile(r"Body Type</[^>]+>\s*<[^>]+>\s*([^<]{2,60}?)\s*<", re.I)
_BODY_CODE = re.compile(r"bodytypeCode:(\d+)")


_FR_PLAYER = re.compile(r"[?&]player=(\d+)")


def player_key(p: Player) -> str:
    """The player (not the card): the base card's id, the player id in the FIFA Rosters address (Icons and
    Heroes have no base card), or the card's own id. Cards with the same key are the same player."""
    if str(p.base_id or "").strip():
        return str(p.base_id)
    m = _FR_PLAYER.search(p.url or "")
    return m.group(1) if m else str(p.id or "")


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
        self.icons: Dict[str, dict] = load_icons(folder)

    def save(self) -> None:
        """Written to a temporary file and moved into place, so a run reading the cache at the same
        time (Evo Lab's deep search while bodies are fetched) never sees half a file."""
        import os
        self.dir.mkdir(parents=True, exist_ok=True)
        for name, data in (("kort.json", self.cards), ("ikoner.json", self.icons)):
            tmp = self.dir / (name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.dir / name)


def load_icons(folder: str) -> Dict[str, dict]:
    """PlayStyle icons seen on FUT.GG pages: {"Name" or "Name+": {"vb": viewBox, "d": [path, ...]}}.
    Only the outline numbers are kept (no markup), so they are safe to draw on our pages."""
    p = Path(folder) / "ikoner.json"
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


_GLYPH = re.compile(r'\s*<svg([^>]*)>(.*?)</svg>', re.S)
_TY = re.compile(r'translate-y-\[(\d{1,3})%\]')


def parse_icons(html: str) -> Dict[str, dict]:
    """The large PlayStyle icons on a card page, as outlines only (no markup).
    On FUT.GG an icon is two SVGs: the frame (diamond = PlayStyle, other shape = PlayStyle+), then the
    symbol in its own SVG, smaller, centred and moved up a bit. Kept: "vb"/"d" for the frame, "gvb"/"g" for
    the symbol, "gs" its size against the frame and "gy" how far up it is moved (per cent of its height)."""
    out: Dict[str, dict] = {}
    for m in _SVG.finditer(html):
        cls, name, attrs, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        h = re.search(r'height="(\d+)"', attrs)
        if cls or not h or int(h.group(1)) < 40:
            continue
        ds = _SVG_D.findall(inner)
        vb = _SVG_VB.search(attrs)
        if not ds or not vb:
            continue
        canon = canonical_playstyle(name) or name
        plus = not ds[0].startswith(_PLAIN)
        rec = {"vb": vb.group(1), "d": ds[:1]}
        g = _GLYPH.match(html, m.end())
        if g:
            gvb, gh = _SVG_VB.search(g.group(1)), re.search(r'height="(\d+)"', g.group(1))
            gd = _SVG_D.findall(g.group(2))
            if gvb and gd:
                ty = _TY.search(g.group(1))
                rec.update(gvb=gvb.group(1), g=gd[:12],
                           gs=round(int(gh.group(1)) / int(h.group(1)), 3) if gh else 0.5,
                           gy=int(ty.group(1)) if ty else 50)
        out[canon + ("+" if plus else "")] = rec
    return out


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
    # alt: all the positions the card can play besides its own (EA's ratings page lists at most three of them)
    return {"r": roles, "p": ids(rp.group(1)) if rp else [], "pp": ids(rp.group(2)) if rp else [],
            "pos": int(pos.group(1)) if pos else None, "alt": ids(pos.group(2)) if pos else None}


def card_image(html: str, card: Optional[str], game: str = "27") -> Optional[str]:
    """The card's background (its rarity) on a FUT.GG player page: the first rarity picture after this card's
    own player picture. The file name carries a hash, so it can only be read from the page."""
    if not card:
        return None
    start = re.search(r"/player-item/%s-%s\." % (re.escape(str(game)), re.escape(str(card))), html)
    m = re.search(r'https://game-assets\.fut\.gg/cdn-cgi/image/[^"\'\s\\<>]*?/20\d\d/rarities-level-\d+-large/\d+\.[0-9a-f]{16,}\.png',
                  html[start.end():] if start else "")
    return re.sub(r"width=\d+", "width=200", m.group(0)) if m else None


def face_image(html: str, card: Optional[str], game: str = "27") -> Optional[str]:
    """This card's own player picture on its FUT.GG page (promo cards often have another picture than the
    base card). The file name carries a hash, so it can only be read from the page."""
    if not card:
        return None
    m = re.search(r'https://game-assets\.fut\.gg/cdn-cgi/image/[^"\'\s\\<>]*?/20\d\d/player-item/%s-%s\.[0-9a-f]{16,}\.webp'
                  % (re.escape(str(game)), re.escape(str(card))), html)
    return re.sub(r"width=\d+", "width=200", m.group(0)) if m else None


def league_image(html: str) -> Optional[str]:
    """The card's league badge (the first league picture of this year's folder on the page)."""
    m = re.search(r'https://game-assets\.fut\.gg/cdn-cgi/image/[^"\'\s\\<>]*?/20\d\d/league/\d+\.[0-9a-f]{16,}\.png', html)
    return m.group(0) if m else None


_FCARD = re.compile(r'class="fc-card [^"]*" style="([^"]{0,300})"')
_CSSVAR = lambda name: re.compile(r'(?:^|;)%s:#([0-9a-fA-F]{6})(?:;|$)' % re.escape(name))
_C_TEXT, _C_FILL, _C_OVR = _CSSVAR("--color"), _CSSVAR("--fill-color"), _CSSVAR("--overall-color")


def card_colors(html: str, card: Optional[str]) -> Optional[str]:
    """The card's own colours as FUT.GG draws it, "text/overall/fill": text for name, stats and the boxes'
    border and letters, overall for rating and position, fill for the boxes and the PlayStyle+ badge.
    Read from the drawn card itself (its style attribute), the one whose picture is this card. (The list of
    the player's other versions on the page has colours too, but from other cards.)"""
    if not card:
        return None
    marks = list(_FCARD.finditer(html))
    for n, m in enumerate(marks):
        end = min(m.end() + 2500, marks[n + 1].start() if n + 1 < len(marks) else len(html))
        if "/player-item/27-%s." % card not in html[m.end():end]:   # only this card's own drawing
            continue
        st = m.group(1)
        t, f, o = _C_TEXT.search(st), _C_FILL.search(st), _C_OVR.search(st)
        if t and f:
            return "/".join(x.group(1).lower() for x in (t, o or t, f))
    return None


_BORN = re.compile(r'(?:dateOfBirth:|"birthDate":)"(\d{4}-\d{2}-\d{2})"')
PARSE_VERSION = 2   # 2: colours from the drawn card, the card's attributes; older records are read again once
_ATTR = re.compile(r'attribute([A-Z][A-Za-z]+):(\d{1,2})\b')
_FACE = re.compile(r'face(Pace|Shooting|Passing|Dribbling|Defending|Physicality):(\d{1,2})\b')
_ATTR_NAMES = {"DefensiveAwareness": "def_awareness"}
_FACE_KEYS = {"Pace": "pac", "Shooting": "sho", "Passing": "pas", "Dribbling": "dri", "Defending": "def", "Physicality": "phy"}


def card_attributes(html: str, card: Optional[str], game: str = "27") -> Optional[dict]:
    """The card's own 34 attributes and six main stats from the page data, {"at": {...}, "fs": {...}}.
    Only the block that belongs to this card (its picture name comes right before it)."""
    if not card:
        return None
    for m in re.finditer(r"attributeAcceleration:", html):
        if "/%s-%s." % (game, card) not in html[max(0, m.start() - 3000):m.start()]:
            continue
        end = html.find("targetFacePace", m.start())
        seg = html[m.start(): end if 0 < end - m.start() < 3000 else m.start() + 2000]
        at = {}
        for name, v in _ATTR.findall(seg):
            key = _ATTR_NAMES.get(name) or re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()
            if key in ATTRIBUTE_LABELS:
                at[key] = float(v)
        fs = {_FACE_KEYS[k]: float(v) for k, v in _FACE.findall(seg)}
        if len(at) >= 29 and len(fs) == 6:
            return {"at": at, "fs": fs}
    return None


def parse_card_page(html: str, card: Optional[str] = None, game: str = "27") -> Optional[dict]:
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
           "height": int(h.group(1)) if h else None, **parse_body(html), "img": card_image(html, card, game), "face": face_image(html, card, game), "lg": league_image(html), "cc": card_colors(html, card),
           "t": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    attrs = card_attributes(html, card, game)
    if attrs:
        rec.update(attrs)
    # date of birth (evos with an age requirement, such as Future Stars Academy, need it)
    b = _BORN.search(html)
    if b:
        rec["born"] = b.group(1)
    rec["v"] = PARSE_VERSION
    if not started:
        rec["no_ps"] = True   # the icons were not found: keep the card's own PlayStyles
    if roles:
        rec["roles"] = roles
    return rec


def parse_body(html: str) -> dict:
    """Body type and weight from the card page: {"bt": "Lean Medium" | the unique model's name | None, "wt": kg}.
    The nine standard bodies are read from bodytypeCode (1-9), unique models from the 'Body Type' text
    (FUT.GG shows the player's name there). "bt" is always set (None when the page has none), so a page
    without a body type is not fetched again for it."""
    import html as _html
    from ..body import CODES, LABEL_NO
    out: dict = {"bt": None}
    c = _BODY_CODE.search(html)
    t = _BODY.search(html)
    code = int(c.group(1)) if c else None
    if code in CODES:
        b, sz = CODES[code]
        out["bt"] = f"{LABEL_NO[b]} {LABEL_NO[sz]}"
    elif t:
        out["bt"] = _html.unescape(t.group(1)).strip() or None
    elif code is not None and code >= 10:
        out["bt"] = "Unique"
    if code is not None:
        out["bc"] = code
    w = _WEIGHT.search(html)
    if w:
        out["wt"] = int(w.group(1))
    return out


def fetch_cards(fetcher, cache: FutggCache, cards: Iterable[Tuple[str, str]], limit: int, game: str = "27",
                log=print, kind: Optional[str] = None, deadline: Optional[float] = None,
                refetch: Optional[set] = None, body: bool = False) -> int:
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
        if deadline is not None and time.time() >= deadline:
            log("  FUT.GG: tiden for denne kjøringen er brukt opp, fortsetter neste kjøring")
            break
        old = cache.cards.get(card)
        # cards fetched before the colours and attributes were read are fetched once more
        again = bool(old) and not old.get("missing") and (int(old.get("v") or 1) < PARSE_VERSION or (
            kind == "base" and card in (refetch or ()) and bool(old.get("roles")) and old["roles"].get("alt") is None)   # fetched before the positions were read, and EA's list may be cut
            or ((kind == "base" or body) and "bt" not in old))   # fetched before body type and weight were read
        if not player or not card or (card in cache.cards and not again):
            continue
        try:
            html = fetcher.get(CARD_URL.format(player=player, game=game, card=card))
            rec = parse_card_page(html, card, game)
            cache.icons.update(parse_icons(html))
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


_GK_FACE = (("div", "pac", "gk_diving"), ("han", "sho", "gk_handling"), ("kic", "pas", "gk_kicking"),
            ("ref", "dri", "gk_reflexes"), ("pos", "phy", "gk_positioning"))


def _half_up(x: float) -> int:
    return int(math.floor(x + 0.5 + 1e-9))


def use_attributes(p: Player, rec: dict) -> bool:
    """FUT.GG's attributes are used when they are this very card: they add up to FUT.GG's own main stats
    (EA's formulas), and those are the card's main stats in our data. A card FUT.GG shows with other
    stats (updated in game since) keeps ours, so the card and its attributes never disagree."""
    at, fs = rec.get("at"), rec.get("fs")
    if not at or not fs:
        return False
    ours = p.face_stats or {}
    if (p.position or "").upper() == "GK":
        pairs = [(ours.get(a, ours.get(b)), at.get(g)) for a, b, g in _GK_FACE]
        return all(x is not None and y is not None and round(float(x)) == round(float(y)) for x, y in pairs)
    from ..model import load_config
    fw = load_config()["weights"]["face_stats"]
    for k, v in fs.items():
        w = {a: c for a, c in (fw.get(k) or {}).items() if not a.startswith("_")}
        if not w or any(a not in at for a in w) or _half_up(sum(at[a] * c for a, c in w.items())) != round(v):
            return False
        if ours.get(k) is None or round(float(ours[k])) != round(v):
            return False
    return True


def apply(players: List[Player], cards: Dict[str, dict], role_positions: Optional[Dict[str, List[int]]] = None) -> int:
    """Use FUT.GG's PlayStyles (and height where missing) on the cards it has. Returns how many.
    Base cards (fetched for their roles) keep EA's PlayStyles. Every card FUT.GG has roles for gets them (+ and ++
    per position); a special card without them keeps ++ in every role of its positions (EA's rule)."""
    n = 0
    for p in players:
        rec = cards.get(str(p.id)) if p.id else None
        if not rec or rec.get("missing"):
            continue
        if rec.get("lg") and str(rec["lg"]).startswith(CARD_IMAGE_HOSTS):
            p.league_image = rec["lg"]
        if rec.get("cc") and re.fullmatch(r"[0-9a-f]{6}/[0-9a-f]{6}/[0-9a-f]{6}", str(rec["cc"])):
            p.card_color = rec["cc"]
        if rec.get("face") and str(rec["face"]).startswith(CARD_IMAGE_HOSTS):
            p.image = rec["face"]   # the card's own picture (promo cards often have another than the base card)
        if use_attributes(p, rec):
            keep = {k: v for k, v in p.attributes.items() if k not in rec["at"]}
            p.attributes = {**{k: float(v) for k, v in rec["at"].items()}, **keep}
            p.estimated = False
        r0 = rec.get("roles") or {}
        if r0.get("alt") is not None and EA_POSITIONS.get(r0.get("pos")) == (p.position or "").upper():
            # FUT.GG has every position the card can play; EA's ratings page only the first three
            p.alt_positions = [EA_POSITIONS[i] for i in r0["alt"] if i in EA_POSITIONS and EA_POSITIONS[i] != (p.position or "").upper()]
            p.positions_complete = True
        # real familiarity (+/++) in every position the card can play, base and special cards alike (20.10: special
        # cards kept only the assumed ++ in the primary position, so Zidane had no role at CM)
        roles = roles_from(rec, role_positions or {}, p.position)
        if roles:
            p.roles, p.roles_complete = roles, True
        if rec.get("kind") != "base" and not rec.get("no_ps"):
            if rec.get("img") and str(rec["img"]).startswith(CARD_IMAGE_HOSTS):
                p.card_image = rec["img"]
            p.playstyles_plus = list(rec.get("psp") or [])
            p.playstyles = [x for x in rec.get("ps") or [] if x not in p.playstyles_plus]
            p.playstyles_complete = True
            p.ps_from_base = False
        if rec.get("height") and not p.height_cm:
            p.height_cm = float(rec["height"])
        if rec.get("bt") and not p.body_type:
            p.body_type = rec["bt"]
        if rec.get("wt") and not p.weight_kg:
            p.weight_kg = float(rec["wt"])
        if rec.get("born") and not p.birthdate:
            p.birthdate = rec["born"]
        n += 1
    return n
