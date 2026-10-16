"""Fetch the official EA SPORTS FC ratings database.

Since FC 27 the player list is read from EA's ratings pages themselves
(ea.com/games/ea-sports-fc/ratings?page=N): each page carries 100 players as
JSON in a <script id="__NEXT_DATA__"> tag, with FC 27 positions, alternative
positions, attributes, PlayStyles, height, weak foot and skill moves. The old
JSON address (drop-api.ea.com) still answers, but with FC 25 cards, so it is
only used when "html_url_template" is removed from config/sources.json.

EA's ratings page (ea.com/games/ea-sports-fc/ratings) loads its player list
from https://drop-api.ea.com/rating/ea-sports-fc?locale=en&limit=100&offset=0
(found in a public FC 25 scraper; set as default in config/sources.json).
EA does not document it, so if it stops working, find the current URL:

  1. Open the ratings page in Chrome or Edge and press F12.
  2. Network tab -> filter "Fetch/XHR" -> scroll the player list.
  3. Click the request that returns the player list, copy its URL.
  4. Replace the page numbers in it with {offset} and {limit}, and paste it
     into "url_template".

The mapper below is deliberately tolerant: it searches each item for anything
that looks like an attribute, position, height, PlayStyle and so on. Run
`python -m fcrating fetch-ea --dump-sample` to save one raw item if a field
is not picked up, then add it under "field_overrides" in sources.json.

The database only covers Gold/Silver/Bronze items (no Icons, Heroes or promo
cards). Be polite: keep the delay between requests.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..schema import Player, canonical_attribute, canonical_playstyle, norm_key, norm_work_rate

SOURCES_FILE = Path(__file__).resolve().parents[2] / "config" / "sources.json"


def load_sources_config(path: Optional[Path] = None) -> dict:
    with open(path or SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _get(url: str, user_agent: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_html(url: str, user_agent: str, timeout: int = 40) -> str:
    import gzip
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html",
                                               "Accept-Language": "en", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")


def next_data(html: str) -> dict:
    """The JSON a Next.js page carries in <script id="__NEXT_DATA__">."""
    import re
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("fant ikke __NEXT_DATA__ på EA-siden (har EA endret siden?)")
    return json.loads(m.group(1))


def _dig(obj: Any, path: str) -> Any:
    for part in [p for p in path.split(".") if p]:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)] if int(part) < len(obj) else None
        else:
            return None
    return obj


def _walk(obj: Any, prefix: str = "") -> Iterable:
    """Yield (path, key, value) for every key in nested dicts/lists."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield p, k, v
            yield from _walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{prefix}.{i}")


def _number(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for key in ("value", "rating", "score"):
            if key in v:
                return _number(v[key])
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _label(v: Any) -> Optional[str]:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for key in ("shortLabel", "label", "name", "id"):
            if isinstance(v.get(key), str):
                return v[key]
    return None


def map_item(item: dict, overrides: Optional[dict] = None) -> Player:
    overrides = overrides or {}
    attrs: Dict[str, float] = {}
    for path, key, value in _walk(item):
        canon = canonical_attribute(key)
        if canon and canon not in ("dribbling",):
            num = _number(value)
            if num is not None and 1 <= num <= 99:
                attrs[canon] = num
    # 'dribbling' is both a face stat and an attribute; prefer a nested stats object
    drib = [(_number(v), p) for p, k, v in _walk(item) if norm_key(k) == "dribbling" and _number(v) is not None]
    if drib:
        attrs["dribbling"] = sorted(drib, key=lambda t: t[1].count("."))[-1][0]

    def pick(*names) -> Any:
        for name in names:
            if name in overrides:
                return _dig(item, overrides[name])
        wanted = [norm_key(n) for n in names]
        for _, key, value in _walk(item):
            if norm_key(key) in wanted and value not in (None, ""):
                return value
        return None

    first = item.get("firstName") if "firstName" not in overrides else pick("firstName")
    last = item.get("lastName") if "lastName" not in overrides else pick("lastName")
    common = item.get("commonName") if "commonName" not in overrides else pick("commonName")
    if isinstance(common, str) and common.strip():
        name = common.strip()
    elif isinstance(first, str) or isinstance(last, str):
        name = " ".join(x.strip() for x in [first, last] if isinstance(x, str) and x.strip())
    else:
        name = item.get("name") if isinstance(item.get("name"), str) else None

    position = _label(pick("position", "preferredPosition")) or ""
    alts = pick("alternatePositions", "altPositions")
    alt_positions = [_label(a) for a in alts] if isinstance(alts, list) else []

    height = pick("height", "heightCm")
    height_cm = _number(height)
    if height_cm is None and isinstance(height, str):
        from .local import _parse_height
        height_cm = _parse_height(height)

    gender_raw = json.dumps(pick("gender", "sex") or "").lower()
    gender = "F" if ("female" in gender_raw or "women" in gender_raw) else "M"

    plus_raw = pick("playStylePlus", "playStylesPlus", "playstyleplus")
    base_raw = pick("playStyle", "playStyles", "playstyles")
    # EA's ratings feed has used one combined list ("playerAbilities") where
    # each entry's label ends with "+" or its type says PlayStyle+.
    combined = pick("playerAbilities", "abilities")

    def ps_names(raw) -> List[str]:
        out = []
        for entry in raw if isinstance(raw, list) else []:
            name_ = canonical_playstyle(_label(entry) or "")
            if name_:
                out.append(name_)
        return out

    plus_list, base_list = ps_names(plus_raw), ps_names(base_raw)
    for entry in combined if isinstance(combined, list) else []:
        label = (_label(entry) or "").strip()
        name_ = canonical_playstyle(label.rstrip("+"))
        if not name_:
            continue
        type_text = norm_key(json.dumps(entry.get("type", "")) if isinstance(entry, dict) else "")
        is_plus = label.endswith("+") or "plus" in type_text
        (plus_list if is_plus else base_list).append(name_)

    face = {}
    for _, key, value in _walk(item):
        k = norm_key(key)
        if k in ("pac", "sho", "pas", "dri", "def", "phy"):
            num = _number(value)
            if num is not None and 1 <= num <= 99:
                face[k] = num

    team, nat = item.get("team"), item.get("nationality")
    club = _label(team) if isinstance(team, dict) else (team if isinstance(team, str) else None)
    nation = _label(nat) if isinstance(nat, dict) else (nat if isinstance(nat, str) else None)
    league = item.get("leagueName") or item.get("league")
    league = _label(league) if isinstance(league, dict) else league

    return Player.from_dict({
        "club": club,
        "league": league if isinstance(league, str) else None,
        "nation": nation,
        "birthdate": pick("birthdate", "birthDate", "dateOfBirth", "dob"),
        "face_stats": face,
        "id": pick("id", "playerId"),
        "name": name or "Ukjent",
        "ovr": _number(pick("overallRating", "overall", "ovr", "rating")),
        "position": str(position).upper(),
        "alt_positions": [a for a in alt_positions if a],
        "gender": gender,
        "height_cm": height_cm,
        "weight_kg": _number(pick("weight", "weightKg")),
        "foot": _label(pick("preferredFoot", "foot")),
        "skill_moves": _number(pick("skillMoves", "skillMovesRating")),
        "weak_foot": _number(pick("weakFootAbility", "weakFoot", "weakFootRating")),
        "attributes": attrs,
        "playstyles_plus": plus_list,
        "playstyles": base_list,
        "roles_complete": False,
        "source": "ea-ratings",
        "work_rate_att": norm_work_rate(pick("attackingWorkRate", "attackWorkRate", "workRateAttack",
                                             "attWorkRate", "attackingWorkrate", "workrateAttacking")),
        "work_rate_def": norm_work_rate(pick("defensiveWorkRate", "defenceWorkRate", "defenseWorkRate",
                                             "workRateDefense", "defWorkRate", "defensiveWorkrate")),
    })


def fetch_pages(ea: dict, max_pages: Optional[int] = None, raw_dir: Optional[str] = None, log=print,
                get=None, sleep=time.sleep) -> List[Player]:
    """All players from EA's ratings pages (?page=1, 2, ...). A page that fails is tried twice more;
    if it still fails, the whole fetch fails, so an older file is never replaced by half a list."""
    get = get or _get_html
    template = ea["html_url_template"]
    items_path = ea.get("html_items_path", "props.pageProps.ratingDetails.items")
    total_path = ea.get("html_total_path", "props.pageProps.ratingDetails.totalItems")
    delay = float(ea.get("delay_seconds", 1.5))
    ua = ea.get("html_user_agent") or "Mozilla/5.0 (compatible; fc27-rating; personlig bruk)"
    overrides = ea.get("field_overrides") or {}
    players: List[Player] = []
    page, per_page, total = 1, None, None
    while True:
        url = template.format(page=page)
        for attempt in range(3):
            try:
                data = next_data(get(url, ua))
                break
            except Exception as exc:  # network hiccup or a page that did not render
                if attempt == 2:
                    raise RuntimeError(f"side {page} feilet: {exc}") from exc
                sleep(5 * (attempt + 1))
        if raw_dir:
            Path(raw_dir).mkdir(parents=True, exist_ok=True)
            with open(Path(raw_dir) / f"ea_side_{page:04d}.json", "w", encoding="utf-8") as f:
                json.dump(_dig(data, items_path), f)
        items = _dig(data, items_path)
        if not isinstance(items, list) or not items:
            break
        if total is None:
            total = _number(_dig(data, total_path))
            per_page = len(items)
        players.extend(map_item(it, overrides) for it in items)
        if page == 1 or page % 20 == 0:
            log(f"  side {page}: {len(players)} av {int(total) if total else '?'} spillere")
        if (total and len(players) >= total) or len(items) < (per_page or 1) or (max_pages and page >= max_pages):
            break
        page += 1
        sleep(delay)
    return players


def fetch_all(cfg: Optional[dict] = None, max_pages: Optional[int] = None,
              raw_dir: Optional[str] = None, log=print) -> List[Player]:
    cfg = cfg or load_sources_config()
    ea = cfg["ea_ratings"]
    if ea.get("html_url_template"):
        return fetch_pages(ea, max_pages=max_pages, raw_dir=raw_dir, log=log)
    template = ea.get("url_template")
    if not template:
        raise RuntimeError("url_template mangler i config/sources.json. Se instruksjonene øverst i "
                           "fcrating/sources/ea_ratings.py eller README.md.")
    limit = int(ea.get("page_size", 100))
    delay = float(ea.get("delay_seconds", 1.5))
    ua = ea.get("user_agent", "fc27-rating (personal use)")
    items_path = ea.get("items_path", "items")
    overrides = ea.get("field_overrides") or {}

    players: List[Player] = []
    offset, page = 0, 0
    while True:
        url = template.format(offset=offset, limit=limit, page=page)
        data = _get(url, ua)
        if raw_dir:
            Path(raw_dir).mkdir(parents=True, exist_ok=True)
            with open(Path(raw_dir) / f"ea_page_{page:04d}.json", "w", encoding="utf-8") as f:
                json.dump(data, f)
        items = _dig(data, items_path) if items_path else data
        if not isinstance(items, list) or not items:
            break
        if page == 0:
            sample = json.dumps(items[:5])
            old = next((tag for tag in ("FC24", "FC25", "FC26") if f"/{tag}/" in sample), None)
            if old:
                log(f"  Merk: EA-adressen ser ut til å gi {old}-kort (bildelenkene inneholder /{old}/). "
                    "FC 27-basekortene bygges derfor fra FIFA Rosters når du kjører fetch-specials.")
        players.extend(map_item(it, overrides) for it in items)
        log(f"  side {page + 1}: {len(items)} spillere (totalt {len(players)})")
        page += 1
        offset += limit
        if len(items) < limit or (max_pages and page >= max_pages):
            break
        time.sleep(delay)
    return players
