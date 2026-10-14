"""Meta: IGR measured against the cards that exist now, the way FUT.GG's GG rating works.

IGR comes from the card's own numbers, so it never changes. Meta does: for every position
we take the average IGR of the best cards (the "meta level", top 50 by default). When better
promo cards arrive, that level rises, and every card in the position loses as much Meta as
the level has risen since the start. A gold striker with IGR 91 shows Meta 91 today, and
Meta 88 once the strikers people actually use have become 3 better.

The start level is kept in data/meta_start.json. It is written once (by the GitHub job with
rate --lagre-meta-start) and then left alone, so all later runs measure against the same start.
Without that file, Meta equals IGR.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {"top": 50, "min_pool": 30}


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
    added = [g for g in current if g not in start]
    if save and added:
        for g in added:
            start[g] = current[g]
        data = {"_info": "Startnivået for Meta: snitt-IGR for de beste kortene i hver posisjon den dagen det ble lagret. "
                         "Meta = IGR minus hvor mye nivået har steget siden. Slett filen for å starte på nytt.",
                "since": data.get("since") or now.strftime("%Y-%m-%d"), "top": settings(cfg)["top"], "levels": start}
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
