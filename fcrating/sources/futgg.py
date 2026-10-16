"""PlayStyles, PlayStyle+, height and weight per card from FUT.GG's card data.

FIFA Rosters has no PlayStyles and EA's FC 27 pages have no height, so special cards
(TOTW, promos) only knew the base card's PlayStyles and many cards had no height.
FUT.GG's card endpoint has both, for every card version:

    https://www.fut.gg/api/fut/player-item-definitions/27/<id>/

<id> is EA's item id: the player id for base cards, the card's own id (the same id
FIFA Rosters calls futid) for special cards. Names for PlayStyle ids come from
https://www.fut.gg/api/fut/playstyles/.

Fetched politely (one request at a time, with a pause, robots.txt respected) and saved in
data/cache/futgg/, so each card is fetched once. Special cards first, then base cards by OVR.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..schema import Player, canonical_playstyle

ITEM_URL = "https://www.fut.gg/api/fut/player-item-definitions/{game}/{id}/"
PS_URL = "https://www.fut.gg/api/fut/playstyles/"


class FutggCache:
    def __init__(self, folder: str):
        self.dir = Path(folder)
        self.cards: Dict[str, dict] = self._load("kort.json")
        self.meta: dict = self._load("meta.json")

    def _load(self, name: str) -> dict:
        p = self.dir / name
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for name, data in (("kort.json", self.cards), ("meta.json", self.meta)):
            with open(self.dir / name, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)


def parse_ps_names(data: dict) -> Dict[str, str]:
    """{"<eaId>": "Finesse Shot"} from the playstyles endpoint."""
    out: Dict[str, str] = {}
    for e in data.get("data") or []:
        if e.get("eaId") is None or not e.get("name") or e.get("isPlayStylePlus"):
            continue
        out.setdefault(str(e["eaId"]), canonical_playstyle(e["name"]) or e["name"])
    return out


def parse_item(data: dict, names: Dict[str, str]) -> Optional[dict]:
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict):
        return None

    def ps(ids) -> List[str]:
        return [names[str(i)] for i in ids or [] if str(i) in names]

    psp = ps(d.get("playstylesPlus"))
    rec = {
        "ps": [x for x in ps(d.get("playstyles")) if x not in psp],
        "psp": psp,
        "unknown_ids": [i for i in (d.get("playstyles") or []) + (d.get("playstylesPlus") or []) if str(i) not in names],
        "height": d.get("height") or None,
        "weight": d.get("weight") or None,
        "acc": (d.get("accelerateType") or "").capitalize() or None,
        "sm": d.get("skillMoves") or None,
        "wf": d.get("weakFoot") or None,
        "ovr": d.get("overall"),
        "t": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    return rec


def ensure_names(fetcher, cache: FutggCache, log=print) -> Dict[str, str]:
    names = cache.meta.get("ps_names") or {}
    if not names:
        names = parse_ps_names(json.loads(fetcher.get(PS_URL)))
        cache.meta["ps_names"] = names
        log(f"FUT.GG: {len(names)} PlayStyle-navn hentet")
    return names


def fetch_items(fetcher, cache: FutggCache, ids: Iterable[str], limit: int, game: str = "27", log=print) -> int:
    """Fetch card data for ids not in the cache yet (in the given order). Returns how many were fetched.
    A card FUT.GG doesn't know (404) is remembered as missing, so it isn't asked for again every run."""
    import urllib.error
    names = ensure_names(fetcher, cache, log)
    done = 0
    for cid in ids:
        cid = str(cid)
        if done >= limit:
            break
        if not cid or cid == "None" or cid in cache.cards:
            continue
        try:
            rec = parse_item(json.loads(fetcher.get(ITEM_URL.format(game=game, id=cid))), names)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            rec = None
        except (ValueError, TimeoutError, OSError) as exc:  # one slow or broken answer: try again next run
            log(f"  FUT.GG: {cid} feilet ({exc}), prøver igjen neste gang")
            continue
        cache.cards[cid] = rec or {"missing": True, "t": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        done += 1
        if done % 50 == 0:
            log(f"  FUT.GG: {done} kort hentet")
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
    """Use FUT.GG's PlayStyles (and height/weight where missing) on cards it knows. Returns how many."""
    n = 0
    for p in players:
        rec = cards.get(str(p.id)) if p.id else None
        if not rec or rec.get("missing"):
            continue
        if rec.get("unknown_ids"):
            continue
        if rec.get("ovr") and p.ovr and int(rec["ovr"]) != int(p.ovr):
            continue  # not the same card version (id mix-up): don't trust it  # a PlayStyle we can't name: keep what we have rather than drop one
        p.playstyles_plus = list(rec.get("psp") or [])
        p.playstyles = [x for x in rec.get("ps") or [] if x not in p.playstyles_plus]
        p.playstyles_complete = True
        p.ps_from_base = False
        if rec.get("height") and not p.height_cm:
            p.height_cm = float(rec["height"])
        if rec.get("weight") and not p.weight_kg:
            p.weight_kg = float(rec["weight"])
        if rec.get("sm") and not p.skill_moves:
            p.skill_moves = int(rec["sm"])
        if rec.get("wf") and not p.weak_foot:
            p.weak_foot = int(rec["wf"])
        n += 1
    return n
