"""Meta: IGR measured against the cards that exist now, the way FUT.GG's GG rating works.

IGR comes from the card's own numbers, so it never changes. Meta does: for every position
we take the average IGR of the best cards (the "meta level", top 50 by default). When better
promo cards arrive, that level rises, and every card in the position loses as much Meta as
the level has risen since the start. A gold striker with IGR 91 shows Meta 91 today, and
Meta 88 once the strikers people actually use have become 3 better.

The start is kept in data/meta_start.json. It is written once (by the GitHub job with
rate --lagre-meta-start) and then left alone, so all later runs measure against the same start.
Without that file, Meta equals IGR.

The file keeps the cards that were the best in each position at the start ("cards"), not only
their IGR. The start level is worked out again on every run, from those cards with today's
formula, so changing how IGR is calculated (PlayStyle values, body type ...) does not look like
the meta moving. Only new, better cards move it. Old files with only "levels" still work.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {"top": 50, "min_pool": 30, "start_cards": 300}


def start_path() -> Path:
    return ROOT / "data" / "meta_start.json"


def settings(cfg: dict) -> dict:
    s = dict(DEFAULTS)
    s.update({k: v for k, v in (cfg.get("weights", {}).get("meta") or {}).items() if not k.startswith("_")})
    return s


def levels(results: List[dict], cfg: dict) -> Dict[str, float]:
    """Average IGR of the best cards in each position. Leaked cards are left out (not in the game yet)."""
    s = settings(cfg)
    pools: Dict[str, List[float]] = {}
    for r in results:
        if r.get("status") == "lekket":
            continue
        for g, e in r["by_group"].items():
            if e.get("igr") is not None:
                pools.setdefault(g, []).append(e["igr"])
    out = {}
    for g, vals in pools.items():
        if len(vals) < s["min_pool"]:
            continue
        top = sorted(vals, reverse=True)[: s["top"]]
        out[g] = round(sum(top) / len(top), 2)
    return out


def _uid(r: dict) -> Optional[str]:
    return r.get("uid")


def start_cards(results: List[dict], cfg: dict) -> Dict[str, List[str]]:
    """The best cards in each position now (more than the top used for the level, so the start
    level can be worked out again when the formula changes the order a little)."""
    s = settings(cfg)
    pools: Dict[str, List[tuple]] = {}
    for r in results:
        if r.get("status") == "lekket" or not _uid(r):
            continue
        for g, e in r["by_group"].items():
            if e.get("igr") is not None:
                pools.setdefault(g, []).append((e["igr"], _uid(r)))
    return {g: [u for _, u in sorted(v, key=lambda t: -t[0])[: s["start_cards"]]]
            for g, v in pools.items() if len(v) >= s["min_pool"]}


def start_levels(results: List[dict], cfg: dict, cards: Dict[str, List[str]]) -> Dict[str, float]:
    """The start level with today's formula: the average IGR of the best of the start cards."""
    s = settings(cfg)
    want = {g: set(v) for g, v in cards.items()}
    pools: Dict[str, List[float]] = {}
    for r in results:
        u = _uid(r)
        if not u:
            continue
        for g, e in r["by_group"].items():
            if u in want.get(g, ()) and e.get("igr") is not None:
                pools.setdefault(g, []).append(e["igr"])
    out = {}
    for g, vals in pools.items():
        if len(vals) < min(s["min_pool"], s["top"]):
            continue
        top = sorted(vals, reverse=True)[: s["top"]]
        out[g] = round(sum(top) / len(top), 2)
    return out


def load_start(path: Optional[Path] = None) -> dict:
    p = Path(path) if path else start_path()
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_start(data: dict, path: Optional[Path] = None) -> Path:
    p = Path(path) if path else start_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return p


def apply(results: List[dict], cfg: dict, path: Optional[Path] = None, save: bool = False,
          now: Optional[datetime] = None) -> dict:
    """Add "meta" to every by_group entry (and pos_meta to each card). Returns what the page shows:
    {"since": date or None, "top": N, "groups": {group: {"now", "start", "drift"}}}.
    save=True writes the start level for positions that have none yet (the first run)."""
    now = now or datetime.now(timezone.utc)
    current = levels(results, cfg)
    data = load_start(path)
    start = dict(data.get("levels") or {})
    cards = dict(data.get("cards") or {})
    if cards:
        # the start cards measured with today's formula (a new formula is not a new meta)
        start.update(start_levels(results, cfg, cards))
    added = [g for g in current if g not in start]
    if save and added:
        now_cards = start_cards(results, cfg) if (cards or not data) else {}
        for g in added:
            start[g] = current[g]
            if g in now_cards:
                cards[g] = now_cards[g]
        data = {"_info": "Startnivået for Meta: de beste kortene i hver posisjon den dagen det ble lagret (cards). "
                         "Nivået regnes ut på nytt hver kjøring fra disse kortene med dagens formel, så endringer i "
                         "IGR-formelen ikke ser ut som at metaen flytter seg. Meta = IGR minus hvor mye nivået har "
                         "steget siden. Slett filen for å starte på nytt.",
                "since": data.get("since") or now.strftime("%Y-%m-%d"), "top": settings(cfg)["top"],
                "levels": {g: v for g, v in start.items()}, **({"cards": cards} if cards else {})}
        save_start(data, path)
    groups = {}
    for g, lv in current.items():
        base = start.get(g)
        drift = round(max(0.0, lv - base), 2) if base is not None else 0.0
        groups[g] = {"now": lv, "start": base, "drift": drift}
    for r in results:
        for g, e in r["by_group"].items():
            if e.get("igr") is None:
                continue
            e["meta"] = round(e["igr"] - groups.get(g, {}).get("drift", 0.0), 1)
        pg = r.get("position_group")
        r["pos_meta"] = r["by_group"].get(pg, {}).get("meta") if pg else None
    return {"since": data.get("since") if start else None, "top": settings(cfg)["top"], "groups": groups,
            "saved": bool(save and added)}
