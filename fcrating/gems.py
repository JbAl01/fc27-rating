"""Skjulte perler: cards that play much better than their OVR says.

For every position, the expected IGR at each OVR is the average IGR of the cards in the position
with about the same OVR. A card is a hidden gem when its IGR is far above that (top few per cent
of the position and at least min_res points), and the page says what lifts it: body type,
PlayStyles, feel, pace and so on, each measured against the same cards. This is the mechanism
behind cards that sell out on the market although their OVR is ordinary (a small, agile body with
Rapid, a 5-star weak foot, the right PlayStyle+ ...). Config: weights.json "hidden_gem".
"""
from __future__ import annotations

import statistics
from typing import Dict, List

# the parts of IGR a card can stand out in (core parts are weighted by the position's blend)
PARTS = [("feel", "følelse"), ("pace", "fart"), ("skill", "ferdigheter"), ("run_score", "løp uten ball"),
         ("stop_score", "vanskelig å stoppe"), ("playstyles", "PlayStyles"), ("body", "kroppstype"),
         ("foot", "svakfot og skill moves"), ("off_balance", "off-balance"), ("role", "rolle")]
CORE = {"feel": "feel", "pace": "pace", "skill": "skill", "run_score": "run", "stop_score": "stop"}


def _parts(e: dict, blend: dict) -> Dict[str, float]:
    out = {}
    for k, _ in PARTS:
        if k == "foot":
            out[k] = (e.get("weak_foot") or 0.0) + (e.get("skill_moves") or 0.0)
        elif k in CORE:
            v = e.get(k)
            if v is not None and blend.get(CORE[k]):
                out[k] = v * blend[CORE[k]]
        else:
            out[k] = e.get(k) or 0.0
    return out


def ovr_share(ovrs_asc: List[int], ovr: int) -> float:
    """Per cent of the position's cards with this OVR or higher: how high the OVR alone puts the card."""
    import bisect
    return 100.0 * (len(ovrs_asc) - bisect.bisect_left(ovrs_asc, ovr)) / len(ovrs_asc) if ovrs_asc else 100.0


def not_hidden_when_used(results: List[dict]) -> None:
    """A card the pros or the FUT.GG teams play is known, so it is no hidden gem (IGR or runs)."""
    for r in results:
        if not r.get("usage"):
            continue
        for e in r["by_group"].values():
            if (e.get("gem") or {}).get("on"):
                e["gem"]["on"] = False
            if (e.get("run") or {}).get("gem"):
                e["run"]["gem"] = False


def add_gems(pools: Dict[str, List[dict]], cfg: dict) -> None:
    """Adds by_group[g]["gem"] = {"res", "top", "on", "why"} to every card in every position."""
    c = {k: v for k, v in (cfg["weights"].get("hidden_gem") or {}).items() if not k.startswith("_")}
    if not c:
        return
    win = int(c.get("ovr_window", 1))
    for g, pool in pools.items():
        cards = [r for r in pool if r.get("status") != "lekket" and r.get("ovr")]
        if len(cards) < c.get("min_pool_size", 30):
            continue
        blend = cfg["weights"]["blend"].get(g, {})
        by_ovr: Dict[int, List[dict]] = {}
        for r in cards:
            by_ovr.setdefault(int(r["ovr"]), []).append(r)
        res_of, why_of = {}, {}
        for o in by_ovr:
            same = [r for x in range(o - win, o + win + 1) for r in by_ovr.get(x, [])]
            if len(same) < c.get("min_same_ovr", 8):
                continue
            exp = statistics.fmean(r["by_group"][g]["igr"] for r in same)
            parts = [_parts(r["by_group"][g], blend) for r in same]
            means = {k: statistics.fmean(p.get(k, 0.0) for p in parts) for k, _ in PARTS}
            for r in by_ovr[o]:
                e = r["by_group"][g]
                res_of[id(r)] = e["igr"] - exp
                mine = _parts(e, blend)
                lift = sorted(((k, mine.get(k, 0.0) - means[k]) for k, _ in PARTS), key=lambda t: -t[1])
                why_of[id(r)] = [k for k, d in lift[:3] if d >= c.get("min_part", 0.5)]
        if not res_of:
            continue
        import bisect
        ovrs = sorted(int(r["ovr"]) for r in cards)
        ovr_cut = float(c.get("ovr_not_top_pct", 0))
        ranked = sorted(res_of.values())
        n = len(ranked)
        labels = dict(PARTS)
        for r in cards:
            res = res_of.get(id(r))
            if res is None:
                continue
            better = n - bisect.bisect_right(ranked, res)
            top = round(100.0 * (better + 1) / n, 1)
            on = (top <= c.get("max_top_pct", 5) and res >= c.get("min_res", 2.5)
                  and ovr_share(ovrs, int(r["ovr"])) > ovr_cut)   # the OVR alone does not show it
            r["by_group"][g]["gem"] = {"res": round(res, 1), "top": top, "on": bool(on),
                                       "why": [labels[k] for k in why_of.get(id(r), [])]}
