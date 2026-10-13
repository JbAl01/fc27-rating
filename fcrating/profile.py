"""Player profile: how a card plays, so you can tell whether you will like it.

Eight categories on the attribute scale (like OVR). Ranking and combinations use
the place among all cards that can play the position, so a 90 card beats a 65
card. The style label ("Kvikk dribler og løper") and what the card suits
("kjappe vendinger", "løp bak backlinja") come from the categories where the
card is best compared with cards in the same position at about the same OVR,
so lower-rated cards get a meaningful style too.

Løps-IQ and Løpseffekt (the two halves of Løps-AI) and Vanskelig å stoppe are
categories too, so they can be filtered and ranked on, but they have "style": false:
they never go into the style label (Løp, Fart and Fysikk already do) or the Profil
panel (the card shows them elsewhere).

Category definitions live in config/weights.json under "profile".
"""
from __future__ import annotations

import bisect
from typing import Dict, List, Optional, Sequence, Tuple

ORDER = ["feel", "pace", "run", "vilje", "effekt", "stopp", "dribble", "finish", "pass", "physical", "defend"]
RUN_PART_SOURCES = {"run_decision": "decision", "run_execution": "execution"}


def order(cfg: dict) -> List[str]:
    """ORDER limited to the categories the config defines (an old config has only eight)."""
    cats = cfg["weights"].get("profile", {}).get("categories", {})
    return [k for k in ORDER if k in cats]


def style_keys(cfg: dict) -> List[str]:
    """Categories that may go into the style label and the Profil panel."""
    cats = cfg["weights"]["profile"]["categories"]
    return [k for k in order(cfg) if cats[k].get("style", True)]


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if not str(k).startswith("_")}


def _weighted(attrs: Dict[str, float], weights: Dict[str, float]) -> Optional[float]:
    w = {k: v for k, v in _clean(weights).items() if k in attrs and v}
    tot = sum(w.values())
    if not w or tot < 0.5 * sum(v for v in _clean(weights).values() if v):
        return None
    return round(sum(attrs[k] * v for k, v in w.items()) / tot, 1)


def categories(r: dict, cfg: dict) -> Dict[str, Optional[float]]:
    """Category values for one rated card (None for goalkeepers)."""
    keys = order(cfg)
    if r.get("position") == "GK":
        return {k: None for k in keys}
    pc = cfg["weights"]["profile"]["categories"]
    attrs = r.get("attributes") or {}
    out: Dict[str, Optional[float]] = {}
    for key in keys:
        c = pc[key]
        src = c.get("source")
        if src == "feel":
            out[key] = r.get("feel")
        elif src == "run":
            out[key] = (r.get("run_ai") or {}).get("score")
        elif src in RUN_PART_SOURCES:
            out[key] = (r.get("run_ai") or {}).get(RUN_PART_SOURCES[src])
        elif src == "stop":
            out[key] = (r.get("hard_to_stop") or {}).get("score")
        else:
            out[key] = _weighted(attrs, c["weights"])
    return out


def _top_pct(sorted_asc: List[float], v: float) -> float:
    better = len(sorted_asc) - bisect.bisect_right(sorted_asc, v)
    return round(100.0 * (better + 1) / len(sorted_asc), 1)


def category_pools(results: List[dict]) -> Dict[str, Dict[str, List[float]]]:
    """Sorted category values per position (everyone who can play it)."""
    pools: Dict[str, Dict[str, List[float]]] = {}
    for r in results:
        for g in r["by_group"]:
            for k, v in (r.get("profile", {}).get("cats") or {}).items():
                if v is not None:
                    pools.setdefault(g, {}).setdefault(k, []).append(v)
    for g in pools:
        for k in pools[g]:
            pools[g][k].sort()
    return pools


def add_profile(results: List[dict], cfg: dict) -> None:
    """r["profile"] = {"cats", "pct" (top % in the position), "lvl" (top % among cards in
    the position with about the same OVR), "style", "likes"}."""
    pcfg = cfg["weights"]["profile"]
    for r in results:
        r["profile"] = {"cats": categories(r, cfg)}
    pools = category_pools(results)
    min_pool = int(pcfg.get("min_pool_size", 30))
    by_ovr: Dict[str, Dict[str, Dict[int, List[float]]]] = {}
    for r in results:
        o = int(r.get("ovr") or 0)
        for g in r["by_group"]:
            for k, v in r["profile"]["cats"].items():
                if v is not None:
                    by_ovr.setdefault(g, {}).setdefault(k, {}).setdefault(o, []).append(v)
    for g in by_ovr:
        for k in by_ovr[g]:
            for o in by_ovr[g][k]:
                by_ovr[g][k][o].sort()
    win0 = int(pcfg.get("style_ovr_window", 2))
    for r in results:
        g = r.get("position_group") or r.get("best_group")
        o = int(r.get("ovr") or 0)
        pct: Dict[str, float] = {}
        lvl: Dict[str, float] = {}
        for k, v in r["profile"]["cats"].items():
            vals = pools.get(g, {}).get(k)
            if v is None or not vals or len(vals) < min_pool:
                continue
            pct[k] = _top_pct(vals, v)
            buckets = by_ovr.get(g, {}).get(k, {})
            w = win0
            while True:
                lists = [buckets[x] for x in range(o - w, o + w + 1) if x in buckets]
                total = sum(len(b) for b in lists)
                if total >= min_pool or w >= 10:
                    break
                w += 1
            if total:
                better = sum(len(b) - bisect.bisect_right(b, v) for b in lists)
                lvl[k] = round(100.0 * (better + 1) / total, 1)
        r["profile"]["pct"], r["profile"]["lvl"] = pct, lvl
        r["profile"]["style"], r["profile"]["likes"] = style(lvl, cfg)


def style(lvl: Dict[str, float], cfg: dict) -> Tuple[str, List[str]]:
    """Style label from the categories where the card is in the top style_top_pct % of
    cards in its position with about the same OVR."""
    if not lvl:
        return "", []
    pcfg = cfg["weights"]["profile"]
    cats = pcfg["categories"]
    thr = float(pcfg.get("style_top_pct", 25))
    allowed = set(style_keys(cfg))
    best = sorted((k for k, p in lvl.items() if p <= thr and k in allowed),
                  key=lambda k: lvl[k])[: int(pcfg.get("max_words", 3))]
    if not best:
        return "Jevn profil", []
    adj = [cats[k]["word"] for k in best if cats[k]["kind"] == "adj"]
    nouns = [cats[k]["word"] for k in best if cats[k]["kind"] == "noun"] or [pcfg.get("default_noun", "spiller")]

    def join(words):
        return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " og " + words[-1]

    label = (join(adj) + " " if adj else "") + join(nouns)
    return label[:1].upper() + label[1:], [cats[k]["like"] for k in best]


def combo_score(r: dict, group: str, chosen: Sequence[str], pools: Dict[str, Dict[str, List[float]]]) -> Optional[float]:
    """100 - average top % in the chosen categories within the position (higher = better)."""
    cats = r.get("profile", {}).get("cats", {})
    pcts = []
    for k in chosen:
        v, vals = cats.get(k), pools.get(group, {}).get(k)
        if v is None or not vals:
            return None
        pcts.append(_top_pct(vals, v))
    return round(100 - sum(pcts) / len(pcts), 1) if pcts else None


def parse_categories(names: Sequence[str], cfg: dict) -> List[str]:
    """'følelse', 'løp', 'Dribling' -> internal keys."""
    cats = cfg["weights"]["profile"]["categories"]
    lookup = {}
    for k, c in cats.items():
        if k.startswith("_"):
            continue
        for alias in [k, c["label"]] + list(c.get("aliases", [])):
            lookup[alias.lower()] = k
    out: List[str] = []
    for n in names:
        for part in str(n).replace(",", " ").split():
            key = lookup.get(part.lower())
            if not key:
                raise ValueError(f"ukjent kategori '{part}'. Bruk: " + ", ".join(
                    c["label"].lower() for k, c in cats.items() if not k.startswith("_")))
            if key not in out:
                out.append(key)
    return out
