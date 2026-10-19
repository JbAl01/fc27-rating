"""Why is a card rated where it is?

For every position pool this compares each card with the average card that can
play the position: percentile of feel, pace and skill, the attributes that
stand out above or below the average, and the bonuses on top. Data is stored
compactly per position (the report turns it into text in the browser), and
`why_lines` turns it into text for the command line.
"""
from __future__ import annotations

import bisect
import statistics
from typing import Dict, List, Optional, Tuple

from .schema import ATTRIBUTE_LABELS

FEEL_KEYS = ["agility", "reactions", "ball_control", "balance", "acceleration", "dribbling", "composure"]


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if not str(k).startswith("_")}


# ---------------------------------------------------------------- missing PlayStyles

def impute_playstyles(pools: Dict[str, List[dict]], cfg: dict) -> None:
    """Cards whose PlayStyles are unknown get the median PlayStyle bonus of
    known cards in the same position with a similar OVR."""
    from .model import tier_for
    mcfg = cfg["weights"].get("playstyles_missing", {})
    if mcfg.get("mode", "median") != "median":
        return
    window = int(mcfg.get("ovr_window", 3))
    min_known = int(mcfg.get("min_known", 20))
    touched = set()
    for g, pool in pools.items():
        known: Dict[int, List[float]] = {}
        for r in pool:
            if r.get("ps_known", True) and r.get("ovr") is not None:
                known.setdefault(int(r["ovr"]), []).append(r["by_group"][g]["playstyles"])
        if not known:
            continue
        all_known = [v for vals in known.values() for v in vals]
        for r in pool:
            if r.get("ps_known", True):
                continue
            entry = r["by_group"][g]
            ovr = int(r["ovr"]) if r.get("ovr") is not None else None
            vals: List[float] = []
            w = window
            while ovr and w <= 12:  # widen the OVR window until there are enough known cards
                vals = [v for o in range(ovr - w, ovr + w + 1) for v in known.get(o, [])]
                if len(vals) >= min_known:
                    break
                w += 1
            median = statistics.median(vals or all_known)
            if median > entry["playstyles"]:
                entry["igr"] = round(entry["igr"] + median - entry["playstyles"], 1)
                entry["playstyles"] = round(median, 2)
                entry["tier"] = tier_for(entry["igr"], cfg["weights"])
            entry["ps_estimated"] = True
            touched.add(id(r))
    for pool in pools.values():
        for r in pool:
            if id(r) in touched:
                best = max(r["by_group"], key=lambda k: r["by_group"][k]["igr"])
                r["best_group"], r["igr"], r["tier"] = best, r["by_group"][best]["igr"], r["by_group"][best]["tier"]


# ---------------------------------------------------------------- explanations

def _pct_top(sorted_vals: List[float], v: Optional[float]) -> Optional[float]:
    if v is None or not sorted_vals:
        return None
    better = len(sorted_vals) - bisect.bisect_right(sorted_vals, v)
    return round(100.0 * (better + 1) / len(sorted_vals), 1)


def explain_keys(g: str, wcfg: dict) -> Tuple[List[str], List[str]]:
    """(skill attributes for the position, all attributes compared in the explanation)."""
    skill_keys = list(_clean(wcfg["skill"][g]))
    keys = list(dict.fromkeys(FEEL_KEYS + ["sprint_speed"] + skill_keys)) if g != "GK" else skill_keys
    return skill_keys, keys


def pool_stats(pool: List[dict], keys: List[str]) -> Dict[str, Tuple[float, float]]:
    """Average and spread of each attribute among the cards that can play the position."""
    stats = {}
    for k in keys:
        vals = [r["attributes"][k] for r in pool if k in r.get("attributes", {})]
        if len(vals) >= 2:
            stats[k] = (statistics.fmean(vals), statistics.pstdev(vals) or 1.0)
    return stats


def _lifts(attrs: dict, weights: Dict[str, float], stats: dict, n: int = 3) -> List[str]:
    """The attributes that lift a score most: weight x (value - position average).
    Without averages (small pools), weight x value."""
    keys = [k for k in weights if k in attrs]
    if stats:
        keys = [k for k in keys if k in stats]
        return sorted(keys, key=lambda k: weights[k] * (attrs[k] - stats[k][0]), reverse=True)[:n]
    return sorted(keys, key=lambda k: weights[k] * attrs[k], reverse=True)[:n]


def add_explanations(pools: Dict[str, List[dict]], cfg: dict) -> None:
    """Store a compact explanation in every by_group entry under "why":
    fp/pp/sp/psp = top % for feel, pace, skill and PlayStyles in the position,
    tf/ts = the attributes that lift feel and skill most [attr, value, average],
    s/w = other attributes clearly above/below the position average [attr, value, average]."""
    wcfg = cfg["weights"]
    ecfg = wcfg.get("explain", {})
    s_z, w_z = ecfg.get("strength_z", 0.6), ecfg.get("weakness_z", -0.6)
    max_s, max_w = ecfg.get("max_strengths", 4), ecfg.get("max_weaknesses", 3)
    min_pool = ecfg.get("min_pool_size", 10)
    feel_w = _clean(wcfg["feel"]["attributes"])

    for g, pool in pools.items():
        skill_keys, keys = explain_keys(g, wcfg)
        skill_w = _clean(wcfg["skill"][g])
        few = len(pool) < min_pool  # too few cards to say what stands out
        stats = {} if few else pool_stats(pool, keys)
        sorted_metric = {m: sorted(r["by_group"][g][m] for r in pool if r["by_group"][g].get(m) is not None)
                         for m in ("feel", "pace", "skill", "playstyles", "run_score", "stop_score")}

        def triple(k, attrs):
            return [k, round(attrs[k]), round(stats[k][0])] if k in stats else [k, round(attrs[k])]

        for r in pool:
            entry = r["by_group"][g]
            attrs = r.get("attributes", {})
            top_feel = _lifts(attrs, feel_w, stats) if g != "GK" else []
            top_skill = _lifts(attrs, skill_w, stats)
            shown = set(top_feel) | set(top_skill) | {"acceleration", "sprint_speed"}
            z = {k: (attrs[k] - m) / sd for k, (m, sd) in stats.items() if k in attrs}
            strengths = sorted((k for k in z if z[k] >= s_z and k not in shown), key=lambda k: z[k], reverse=True)[:max_s]
            weaknesses = sorted((k for k in z if z[k] <= w_z and k in skill_keys + FEEL_KEYS), key=lambda k: z[k])[:max_w]
            pct = (lambda m, v: None) if few else (lambda m, v: _pct_top(sorted_metric[m], v))
            entry["why"] = {
                "fp": pct("feel", entry.get("feel")) if g != "GK" else None,
                "pp": pct("pace", entry.get("pace")),
                "sp": pct("skill", entry.get("skill")),
                "psp": pct("playstyles", entry.get("playstyles")),
                "rp": pct("run_score", entry.get("run_score")),
                "stp": pct("stop_score", entry.get("stop_score")),
                "tf": [triple(k, attrs) for k in top_feel],
                "ts": [triple(k, attrs) for k in top_skill],
                "s": [triple(k, attrs) for k in strengths],
                "w": [triple(k, attrs) for k in weaknesses],
            }
            if few:
                entry["why"]["few"] = 1


def _pct_text(p: Optional[float]) -> str:
    if p is None:
        return ""
    return "topp <1 %" if p < 1 else f"topp {p:.0f} %"


def _paren(p: Optional[float], suffix: str = "") -> str:
    return f" ({_pct_text(p)}{suffix})" if p is not None else ""


def summary(e: dict, blend: dict) -> Tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
    """What lifts the card (top 25 % or better in the position) and what holds it back
    (outside the top 60 %). Same logic as the report page."""
    w = e.get("why") or {}
    parts = [("følelse", w.get("fp"), blend.get("feel", 0)), ("fart", w.get("pp"), blend.get("pace", 0)),
             ("ferdighet", w.get("sp"), blend.get("skill", 0)), ("løps-AI", w.get("rp"), blend.get("run", 0)),
             ("vanskelig å stoppe", w.get("stp"), blend.get("stop", 0)),
             ("PlayStyles", w.get("psp"), 1.0)]
    parts = [(n, p, wt) for n, p, wt in parts if p is not None and wt > 0]
    up = sorted(((n, p) for n, p, wt in parts if p <= 25), key=lambda x: x[1])[:2]
    down = sorted(((n, p) for n, p, wt in parts if p >= 60 and wt >= 0.12), key=lambda x: -x[1])[:2]
    return up, down


def why_lines(r: dict, g: str, blend: Optional[dict] = None) -> List[str]:
    """Plain text explanation for one card in one position."""
    from .schema import GROUP_PLURAL_NO
    e = r["by_group"][g]
    w = e.get("why") or {}
    blend = blend or {}
    lab = ATTRIBUTE_LABELS.get
    plural = GROUP_PLURAL_NO.get(g, g)
    lines = []

    def attr_list(items):
        return ", ".join(f"{lab(x[0], x[0])} {x[1]:.0f}" + (f" (snitt {x[2]})" if len(x) > 2 else "") for x in items)

    def join(items):
        return " og ".join(f"{n} ({_pct_text(p)})" for n, p in items)

    if e.get("rank") and w.get("few"):
        lines.append(f"Plass {e['rank']} av {e['of']} {plural}. For få {plural} i dataene til å si hva som "
                     "skiller seg ut (prosenter vises når flere kort er med).")
    elif e.get("rank"):
        up, down = summary(e, blend)
        text = f"Plass {e['rank']} av {e['of']} {plural}{_paren(e.get('top_pct'))}. "
        text += f"Mest pga. {join(up)}." if up else "Ingen del er blant de 25 % beste i posisjonen."
        if down:
            text += f" Trekkes ned av {join(down)}."
        lines.append(text)
    bonus = (e.get("role", 0) + e.get("weak_foot", 0) + e.get("skill_moves", 0) + e.get("gk_height", 0)
             + e.get("off_balance", 0) + e.get("stand_tackle", 0) + e.get("body", 0))
    core_parts = []
    if blend.get("feel") and e.get("feel") is not None:
        core_parts.append(f"følelse {e['feel']:.1f} x {blend['feel'] * 100:.0f} %")
    if blend.get("pace") and e.get("pace") is not None:
        core_parts.append(f"fart {e['pace']:.1f} x {blend['pace'] * 100:.0f} %")
    core_parts.append(f"ferdighet {e['skill']:.1f} x {blend.get('skill', 1) * 100:.0f} %")
    if blend.get("run") and e.get("run_score") is not None:
        core_parts.append(f"løps-AI {e['run_score']:.1f} x {blend['run'] * 100:.0f} %")
    if blend.get("stop") and e.get("stop_score") is not None:
        core_parts.append(f"stopp {e['stop_score']:.1f} x {blend['stop'] * 100:.0f} %")
    lines.append(f"IGR {e['igr']:.1f} = kjerne {e.get('core', 0):.1f} ({' + '.join(core_parts)}) "
                 f"{e['playstyles']:+.1f} PlayStyles {bonus:+.1f} bonuser")
    if e.get("feel") is not None and g != "GK":
        lines.append(f"Følelse {e['feel']:.1f}{_paren(w.get('fp'), ' av ' + plural)}"
                     + (f": {attr_list(w.get('tf', []))}" if w.get("tf") else ""))
    if e.get("pace") is not None:
        acc, spr = r["attributes"].get("acceleration"), r["attributes"].get("sprint_speed")
        lines.append(f"Fart {e['pace']:.1f}{_paren(w.get('pp'))}"
                     + (f": Acceleration {acc:.0f}, Sprint Speed {spr:.0f}" if acc and spr else ""))
    lines.append(f"Posisjonsferdighet {e['skill']:.1f}{_paren(w.get('sp'))}"
                 + (f": {attr_list(w.get('ts', []))}" if w.get("ts") else ""))
    fp = r.get("feel_parts", {})
    body = []
    if r.get("height_cm"):
        body.append(f"{r['height_cm']:.0f} cm" + (f" ({fp.get('height', 0):+.1f} følelse)" if fp.get("height") else ""))
    if r.get("accelerate"):
        body.append(f"{r['accelerate']}" + (f" ({fp.get('accelerate', 0):+.1f} følelse)" if fp.get("accelerate") else ""))
    bd = e.get("body_detail")
    if bd:
        part = [f"{bd['frame']:+.1f} for kroppen"]
        if bd["amp"]:
            part.append(f"{bd['amp']:+.1f} fordi kroppen forsterker smidigheten")
        if bd["combo"]:
            part.append(f"{bd['combo']:+.1f} sammen med PlayStyles")
        body.insert(0, f"{bd['label']} ({e['body']:+.1f}: {', '.join(part)})")
    elif g != "GK":
        body.insert(0, "kroppstype ikke hentet ennå")
    if body:
        lines.append("Kropp: " + ", ".join(body))
    if e.get("ps_estimated"):
        lines.append(f"PlayStyles {e['playstyles']:+.1f}: ukjent for dette kortet, anslått som medianen for "
                     f"{plural} med lignende OVR")
    elif e.get("playstyle_details"):
        top = ", ".join(f"{d['name']} ({d['points']:+.1f})" for d in e["playstyle_details"][:5] if round(d["points"], 1) > 0)
        lines.append(f"PlayStyles {e['playstyles']:+.1f}{_paren(w.get('psp'))}" + (f": {top}" if top else ""))
    extras = []
    if e.get("role"):
        extras.append(f"rolle {e.get('role_name') or ''} ({e['role']:+.0f})")
    if r.get("weak_foot") and e.get("weak_foot"):
        extras.append(f"svakfot {r['weak_foot']}★ ({e['weak_foot']:+.1f})")
    if r.get("skill_moves") and e.get("skill_moves"):
        extras.append(f"skill moves {r['skill_moves']}★ ({e['skill_moves']:+.1f})")
    if e.get("gk_height"):
        extras.append(f"høyde ({e['gk_height']:+.1f})")
    if e.get("off_balance"):
        extras.append(f"off-balance dribbling {r.get('off_balance_dribbling') or 0:.0f} ({e['off_balance']:+.1f})")
    if e.get("stand_tackle"):
        st = r.get("attributes", {}).get("standing_tackle", 0)
        extras.append(f"Standing Tackle {st:.0f} ({'alle' if st >= 85 else 'bare enkle'} taklingsanimasjoner, "
                      f"{e['stand_tackle']:+.1f})")
    if extras:
        lines.append("Bonuser: " + ", ".join(extras))
    if w.get("s"):
        lines.append("Skiller seg også ut: " + attr_list(w["s"]))
    if w.get("w"):
        lines.append("Svakere enn snittet: " + attr_list(w["w"]))
    return lines
