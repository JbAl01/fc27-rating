"""Løps-AI: how well a forward moves without the ball.

EA has never published how off-ball runs are decided, and the role you pick
is the same for every card (most cards can get ++). So this score uses only
what differs between cards:

  * Att. Position         - how often and how cleverly the player goes into space
                            (FC 27: Attacking Spatial Awareness decides where the run goes)
  * Acceleration          - the first 5-15 m; FC 27 runs are short and curved, and
                            manual runs stop after a set distance, so this counts most
  * Sprint Speed          - keeping the separation once it is made
  * Reactions             - how fast the run starts
  * Agility / Balance     - taking the curve of the run, keeping speed through contact
  * Strength              - not being knocked off during the run
  * Stamina               - only AI-controlled players slow down when tired, and the
                            off-ball runs are made by the AI
  Ball Control / Composure are kept at weight 0: they decide the first touch after the
  player is free, not whether the run creates space, and they already count in feel.
  * kort_kropp            - real height turned into a 0-99 value (short = high):
                            small players get free more often on the same run
  * kvikk_sterk = min(Agility, Strength): agile AND strong is rare (Geyse FC 25)
  * arbeidsrate = the old attacking work rate (H/M/L). EA replaced work rates
    with roles in FC 25, but the value is still in the card data. Whether the
    game still uses it is unknown, which is what `kalibrer` can test.

Score = weighted average of the features (attribute scale), so it reads like
OVR. It is split in two parts that can be checked separately:
  Løps-IQ (decision_features: Att. Position, Reactions) - where and when the player runs.
    Called Løpsvilje before. How OFTEN a player runs was the work rate up to FC 24 and is
    the role and its familiarity (+/++) from FC 25 (EA: familiarity gives better types and
    timing of runs), so the card part is the intelligence, not the volume.
  Løpseffekt (everything else) - does the run create a chance? Weights live in config/weights.json under run_ai and can be replaced by a
calibration from your own counted runs (config/run_ai_kalibrert.json).
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .schema import ATTRIBUTE_LABELS, norm_work_rate

CALIBRATION_FILE = "run_ai_kalibrert.json"
FEATURE_LABELS = dict(ATTRIBUTE_LABELS, kvikk_sterk="Kvikk og sterk", balanse_sterk="Balanse og sterk",
                      arbeidsrate="Arbeidsrate (angrep)", kort_kropp="Lav høyde",
                      height_cm="Høyde")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if not str(k).startswith("_")}


def run_cfg(cfg: dict) -> dict:
    return cfg["weights"]["run_ai"]


def load_calibration(cfg: dict, config_dir: Path) -> None:
    """Replace the run_ai weights with calibrated ones if the file exists."""
    path = Path(config_dir) / CALIBRATION_FILE
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        cal = json.load(f)
    rc = run_cfg(cfg)
    rc["default_weights"] = dict(_clean(rc["weights"]))
    rc["weights"] = cal["weights"]
    rc["calibrated"] = {k: v for k, v in cal.items() if k != "weights"}


# ---------------------------------------------------------------- features

def short_body_value(height_cm: Optional[float], rc: dict) -> Optional[float]:
    """Real height (also for women, like the animations) on the attribute scale:
    175 cm = 80, one point per cm, so 165 cm = 90 and 190 cm = 65."""
    if not height_cm:
        return None
    c = _clean(rc["short_body"])
    return max(c["min"], min(c["max"], c["ref_value"] - (height_cm - c["ref_cm"]) * c["per_cm"]))


def decision_keys(rc: dict) -> List[str]:
    return list(rc.get("decision_features", ["positioning", "reactions", "arbeidsrate"]))


def features(attrs: Dict[str, float], work_rate_att: Optional[str], rc: dict,
             height_cm: Optional[float] = None) -> Dict[str, float]:
    """All features on the attribute scale (0-99). Missing ones are left out."""
    f = {k: float(v) for k, v in attrs.items() if v}
    hb = short_body_value(height_cm, rc)
    if hb is not None:
        f["kort_kropp"] = hb
    if "agility" in f and "strength" in f:
        f["kvikk_sterk"] = min(f["agility"], f["strength"])
    if "balance" in f and "strength" in f:
        f["balanse_sterk"] = min(f["balance"], f["strength"])
    wr = norm_work_rate(work_rate_att)
    if wr:
        f["arbeidsrate"] = float(_clean(rc["work_rate_values"])[wr])
    return f


def score(feats: Dict[str, float], weights: Dict[str, float]) -> Tuple[Optional[float], List[list]]:
    """Weighted average over the features that exist. Returns (score, parts) where
    parts = [feature, value, weight share, points] sorted by points."""
    w = {k: v for k, v in _clean(weights).items() if v and k in feats}
    total = sum(w.values())
    if not w or total < 0.5 * sum(v for v in _clean(weights).values() if v):
        return None, []
    parts = [[k, round(feats[k]), round(v / total, 3), round(feats[k] * v / total, 2)] for k, v in w.items()]
    parts.sort(key=lambda x: x[3], reverse=True)
    return round(sum(x[3] for x in parts), 1), parts


def sub_scores(feats: Dict[str, float], weights: Dict[str, float], rc: dict) -> Tuple[Optional[float], Optional[float]]:
    """(Løps-IQ, Løpseffekt): the score over the decision features and over the rest."""
    dk = set(decision_keys(rc))
    dec = score(feats, {k: v for k, v in weights.items() if k in dk})[0]
    exe = score(feats, {k: v for k, v in weights.items() if k not in dk})[0]
    return dec, exe


def card_run_score(attrs: Dict[str, float], work_rate_att: Optional[str], height_cm: Optional[float],
                   cfg: dict) -> Optional[float]:
    """Løps-AI for one card, used inside IGR for the run positions."""
    rc = cfg["weights"].get("run_ai")
    if not rc:
        return None
    return score(features(attrs, work_rate_att, rc, height_cm), _clean(rc["weights"]))[0]


def body_label(attrs: Dict[str, float], height_cm: Optional[float], rc: dict) -> str:
    """Rough animation profile from real height, Agility and Strength."""
    b = _clean(rc["body"])
    agi, strn = attrs.get("agility", 0), attrs.get("strength", 0)
    if agi >= b["quick"] and strn >= b["strong"]:
        return "Kvikk og sterk"
    if height_cm and height_cm <= b["small_cm"] and agi >= b["quick"]:
        return "Liten og kvikk"
    if (height_cm and height_cm >= b["big_cm"]) or strn - agi >= b["heavy_gap"]:
        return "Stor og tung"
    return "Balansert"


# ---------------------------------------------------------------- ranking

def _top_pct(sorted_desc: List[float], v: float) -> float:
    import bisect
    asc = sorted_desc[::-1]
    better = len(asc) - bisect.bisect_right(asc, v)
    return round(100.0 * (better + 1) / len(asc), 1)


NO_RUN = ("GK", "CB")   # no runs worth measuring


def add_run_ai(results: List[dict], cfg: dict) -> None:
    """Adds r["run_ai"] = {score, parts, body, wr, vs_ovr} and, for ST/W/CAM,
    by_group[g]["run"] = {rank, of, top_pct, ovr_top_pct, gem, up, down} where
    up/down = the features that lift the card most above / pull it most below
    the average card in the position: [feature, value, position average]."""
    rc = run_cfg(cfg)
    groups = rc.get("groups", ["ST", "W", "CAM"])
    gem = _clean(rc["gem"])
    # A work rate that (almost) every card shares says nothing about the card, and it
    # would only pull cards that have it slightly away from cards that don't.
    rc["dropped"] = {}
    wrs = [norm_work_rate(r.get("work_rate_att")) for r in results if any(g in r["by_group"] for g in groups)]
    wrs = [w for w in wrs if w]
    if wrs:
        mode = max(set(wrs), key=wrs.count)
        share = wrs.count(mode) / len(wrs)
        if share >= float(rc.get("constant_share", 0.9)):
            rc["dropped"]["arbeidsrate"] = f"{share:.0%} av kortene har arbeidsrate {mode}"
    weights = {k: v for k, v in _clean(rc["weights"]).items() if k not in rc["dropped"]}
    feats_of: Dict[int, Dict[str, float]] = {}
    for r in results:
        # every card that can play in front of the centre backs gets its Løps-AI (shown for CM, CDM and backs too);
        # IGR uses it only in `groups`
        if not any(g not in NO_RUN for g in r["by_group"]):
            r["run_ai"] = None
            continue
        feats = features(r.get("attributes") or {}, r.get("work_rate_att"), rc, r.get("height_cm"))
        s, parts = score(feats, weights)
        if s is None:
            r["run_ai"] = None
            continue
        feats_of[id(r)] = feats
        dec, exe = sub_scores(feats, weights, rc)
        r["run_ai"] = {
            "score": s, "parts": parts, "vs_ovr": round(s - r["ovr"], 1) if r.get("ovr") else None,
            "decision": dec, "execution": exe,
            "body": body_label(r.get("attributes") or {}, r.get("height_cm"), rc),
            "wr": f"{r.get('work_rate_att') or '?'}/{r.get('work_rate_def') or '?'}",
        }
    for g in groups:
        pool = [r for r in results if g in r["by_group"] and r.get("run_ai")]
        if not pool:
            continue
        means = {}
        for k in weights:
            vals = [feats_of[id(r)][k] for r in pool if k in feats_of[id(r)]]
            if vals:
                means[k] = statistics.fmean(vals)
        runs = sorted((r["run_ai"]["score"] for r in pool), reverse=True)
        ovrs = sorted((r["ovr"] or 0 for r in pool), reverse=True)
        from .gems import ovr_share
        ovrs_asc = sorted(int(r["ovr"] or 0) for r in pool)
        ovr_cut = float(((cfg["weights"].get("hidden_gem") or {}).get("ovr_not_top_pct")) or 0)
        # expected Løps-AI for each OVR = average of cards in the position with OVR within the window
        by_ovr: Dict[int, List[float]] = {}
        for r in pool:
            by_ovr.setdefault(int(r["ovr"] or 0), []).append(r["run_ai"]["score"])
        win = int(gem.get("ovr_window", 1))
        expected, same = {}, {}
        for o in by_ovr:
            vals = [v for x in range(o - win, o + win + 1) for v in by_ovr.get(x, [])]
            expected[o], same[o] = statistics.fmean(vals), len(vals)
        res_of = {id(r): r["run_ai"]["score"] - expected[int(r["ovr"] or 0)] for r in pool}
        res_sorted = sorted(res_of.values(), reverse=True)
        pool.sort(key=lambda r: r["run_ai"]["score"], reverse=True)
        n = len(pool)
        for i, r in enumerate(pool, 1):
            f = feats_of[id(r)]
            share = {k: w for k, w, in ((x[0], x[2]) for x in r["run_ai"]["parts"])}
            lift = sorted(((k, share[k] * (f[k] - means[k])) for k in share if k in means), key=lambda t: t[1], reverse=True)
            top = _top_pct(runs, r["run_ai"]["score"])
            ovr_top = _top_pct(ovrs, r["ovr"] or 0)
            res = res_of[id(r)]
            res_top = _top_pct(res_sorted, res)
            r["by_group"][g]["run"] = {
                "rank": i, "of": n, "top_pct": top, "ovr_top_pct": ovr_top,
                "res": round(res, 1), "res_top_pct": res_top,
                "gem": bool(n >= gem["min_pool_size"] and same[int(r["ovr"] or 0)] >= gem.get("min_same_ovr", 8)
                            and res_top <= gem["max_res_top_pct"]
                            and res >= gem["min_res"] and top <= gem["max_run_top_pct"]
                            and ovr_share(ovrs_asc, int(r["ovr"] or 0)) > ovr_cut),
                "up": [[k, round(f[k]), round(means[k])] for k, c in lift[:3] if c > 0.05],
                "down": [[k, round(f[k]), round(means[k])] for k, c in lift[::-1][:2] if c < -0.05],
            }


def run_group(r: dict, groups: Sequence[str]) -> Optional[str]:
    """The card's own position if it is a run position, else its best run position."""
    g = r.get("position_group")
    if g in groups and "run" in r["by_group"].get(g, {}):
        return g
    cands = [x for x in groups if "run" in r["by_group"].get(x, {})]
    return min(cands, key=lambda x: r["by_group"][x]["run"]["top_pct"]) if cands else None


# ---------------------------------------------------------------- similar cards

def _sim_keys(rc: dict) -> List[str]:
    return list(_clean(rc["similar"]["features"]))


PS_SD = 0.5   # 'playstyles': (1 - share in common) / PS_SD, so no PlayStyle in common = 2 standard deviations


def similarity_stats(results: List[dict], rc: dict) -> Dict[str, Tuple[float, float]]:
    """Mean and spread of every similarity number over all outfield cards. (The run calibration's dropped
    features are about the run score, not about how alike two cards are, so they stay in.)"""
    keys = _sim_keys(rc)
    pool = [r for r in results if (r.get("position") or "").upper() != "GK"]
    out = {}
    for k in keys:
        if k == "playstyles":
            if any(ps_set(r) for r in pool[:2000]):
                out[k] = (0.0, PS_SD)
            continue
        vals = [_sim_value(r, k, rc) for r in pool]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 2:
            fixed = (rc["similar"].get("fixed_sd") or {}).get(k)
            out[k] = (statistics.fmean(vals), float(fixed) if fixed else (statistics.pstdev(vals) or 1.0))
    return out


def ps_set(r: dict) -> set:
    """The card's PlayStyles (PS+ as the same PlayStyle), empty when unknown."""
    if not r.get("ps_known", True):
        return set()
    for v in (r.get("by_group") or {}).values():
        return {d["name"].rstrip("+") for d in v.get("playstyle_details", [])}
    return set()


def ps_overlap_z(a: set, b: set) -> Optional[float]:
    if not a or not b:
        return None
    return (1.0 - len(a & b) / len(a | b)) / PS_SD


def _sim_value(r: dict, key: str, rc: dict) -> Optional[float]:
    if key == "height_cm":
        return r.get("height_cm")
    if key == "arbeidsrate":
        wr = norm_work_rate(r.get("work_rate_att"))
        return float(_clean(rc["work_rate_values"])[wr]) if wr else None
    if key == "kvikk_sterk":
        a = r.get("attributes") or {}
        return min(a["agility"], a["strength"]) if "agility" in a and "strength" in a else None
    if key == "kort_kropp":
        return short_body_value(r.get("height_cm"), rc)
    if key == "accelerate":
        v = _clean(rc["similar"].get("accelerate_values", {})).get(r.get("accelerate") or "")
        return float(v) if v is not None else None
    if key == "folelse":
        return r.get("feel")
    if key == "vekt":
        return r.get("weight_kg")
    if key == "playstyles":
        return None   # a set, compared in distance()
    if key in ("kropp", "unik"):   # body type (body.frame_code): build on a 0-100 scale, and unique model or not
        fc = r.get("frame")
        if not fc:
            return None
        return float(rc["similar"]["build_values"][fc[0]]) if key == "kropp" else (100.0 if fc[2] else 0.0)
    return (r.get("attributes") or {}).get(key)


def distance(a: dict, b: dict, stats: Dict[str, Tuple[float, float]], rc: dict) -> Optional[float]:
    fw = _clean(rc["similar"]["features"])
    zmax = float(rc["similar"].get("max_z", 3.0))
    total, used = 0.0, 0.0
    for k, (m, sd) in stats.items():
        if k == "playstyles":
            z = ps_overlap_z(ps_set(a), ps_set(b))
            if z is not None:
                total += fw[k] * min(z, zmax) ** 2
                used += fw[k]
            continue
        va, vb = _sim_value(a, k, rc), _sim_value(b, k, rc)
        if k in rc["similar"].get("impute", ()):   # unknown body or weight: an average card there, not a free pass
            va, vb = (m if va is None else va), (m if vb is None else vb)
        if va is None or vb is None:
            continue
        total += fw[k] * min(abs(va - vb) / sd, zmax) ** 2
        used += fw[k]
    if used < 0.5 * sum(fw.values()):
        return None
    return math.sqrt(total / used)


def similarity_pct(d: float) -> int:
    return round(100 * math.exp(-d / 1.2))


def similar_to_all(refs: List[dict], results: List[dict], cfg: dict, n: int = 10,
                   group: Optional[str] = None) -> List[Tuple[dict, float]]:
    """Cards closest to all reference cards at once (average distance)."""
    if len(refs) == 1:
        return similar(refs[0], results, cfg, n=n, group=group)
    rc = run_cfg(cfg)
    stats = similarity_stats(results, rc)
    ref_ids = {id(r) for r in refs}
    ref_keys = {(r["name"], r.get("rarity")) for r in refs}
    out = []
    for r in results:
        if id(r) in ref_ids or not r.get("run_ai") or (r["name"], r.get("rarity")) in ref_keys:
            continue
        if group and "run" not in r["by_group"].get(group, {}):
            continue
        ds = [distance(ref, r, stats, rc) for ref in refs]
        if any(d is None for d in ds):
            continue
        out.append((r, sum(ds) / len(ds)))
    out.sort(key=lambda t: t[1])
    return out[:n]


def similar(ref: dict, results: List[dict], cfg: dict, n: int = 10, group: Optional[str] = None) -> List[Tuple[dict, float]]:
    """Closest run profiles. With group, only cards that can play that run position."""
    rc = run_cfg(cfg)
    stats = similarity_stats(results, rc)
    out = []
    for r in results:
        if r is ref or not r.get("run_ai") or (r["name"] == ref["name"] and r.get("rarity") == ref.get("rarity")):
            continue
        if group and "run" not in r["by_group"].get(group, {}):
            continue
        d = distance(ref, r, stats, rc)
        if d is not None:
            out.append((r, d))
    out.sort(key=lambda t: t[1])
    return out[:n]


# ---------------------------------------------------------------- explanation

def run_lines(r: dict, g: str, plural: str) -> List[str]:
    ra = r.get("run_ai")
    if not ra:
        return []
    run = r["by_group"].get(g, {}).get("run", {})
    lines = []
    head = f"Løps-AI {ra['score']:.1f}"
    if run:
        head += f": plass {run['rank']} av {run['of']} {plural} (topp {run['top_pct']:.0f} %)"
        head += f". {run['res']:+.1f} mot snittet for {plural} med samme OVR"
    lines.append(head)
    if ra.get("decision") is not None or ra.get("execution") is not None:
        fmt = lambda v: f"{v:.1f}" if v is not None else "?"
        lines.append(f"Løps-IQ {fmt(ra.get('decision'))} (hvor og når spilleren løper: Att. Position, Reactions) · "
                     f"Løpseffekt {fmt(ra.get('execution'))} (om løpet skaper avstand: fart, smidighet, kropp, høyde, Stamina)")
    if run.get("gem"):
        lines.append(f"SKJULT PERLE: løper bedre enn {min(99, int(100 - run['res_top_pct']))} % av {plural}, sammenlignet med kort med samme OVR")
    def fl(items):
        return ", ".join(f"{FEATURE_LABELS.get(k, k)} {v} (snitt {m})" for k, v, m in items)
    if run.get("up"):
        lines.append(f"Løfter mest: {fl(run['up'])}")
    if run.get("down"):
        lines.append(f"Trekker ned: {fl(run['down'])}")
    lines.append(f"Kropp: {ra['body']}" + (f", {r['height_cm']:.0f} cm" if r.get("height_cm") else "")
                 + f". Arbeidsrate: {ra['wr']}")
    return lines


# ---------------------------------------------------------------- calibration

def _ranks(xs: Sequence[float]) -> List[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 3:
        return None
    rx, ry = _ranks(x), _ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if not sx or not sy:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy), 2)


def _solve(a: List[List[float]], b: List[float]) -> List[float]:
    """Gaussian elimination with partial pivoting (small systems)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _ridge(X: List[List[float]], y: List[float], lam: float) -> List[float]:
    p = len(X[0])
    xtx = [[sum(row[i] * row[j] for row in X) + (lam if i == j else 0.0) for j in range(p)] for i in range(p)]
    xty = [sum(row[i] * yy for row, yy in zip(X, y)) for i in range(p)]
    return _solve(xtx, xty)


def calibrate(labeled: List[Tuple[dict, float]], cfg: dict, only: Optional[Sequence[str]] = None) -> dict:
    """labeled = [(rated result, label)], label = counted runs or a 0-1 / 1-5 grade.
    With only, just those features are compared and fitted (e.g. the Løpsvilje
    features against runs started, the Løpseffekt features against the share of
    runs where the player got free); the returned weights then sum to 1 over them.

    Returns correlations per feature, how well OVR and the current Løps-AI order
    the cards, fitted weights (ridge on standardized features, negatives set to 0,
    shrunk toward the current weights when there are few cards) and a
    leave-one-out check of the fitted weights."""
    rc = run_cfg(cfg)
    old = _clean(rc["weights"])
    if only is not None:
        old = {k: v for k, v in old.items() if k in set(only)}
        tot = sum(old.values()) or 1.0
        old = {k: v / tot for k, v in old.items()}
    keys = list(old)
    feats = [features(r.get("attributes") or {}, r.get("work_rate_att"), rc, r.get("height_cm")) for r, _ in labeled]
    y = [float(l) for _, l in labeled]
    n = len(y)

    corr = {}
    for k in keys:
        pairs = [(f[k], yy) for f, yy in zip(feats, y) if k in f]
        if len(pairs) >= 3:
            c = spearman([a for a, _ in pairs], [b for _, b in pairs])
            if c is not None:
                corr[k] = (c, len(pairs))
    corr_ovr = spearman([r.get("ovr") or 0 for r, _ in labeled], y)
    corr_now = spearman([score(f, old)[0] or 0 for f in feats], y)

    usable = [k for k in keys if k in corr and corr[k][1] >= max(3, int(0.7 * n))]
    means = {k: statistics.fmean([f[k] for f in feats if k in f]) for k in usable}
    sds = {k: statistics.pstdev([f[k] for f in feats if k in f]) or 1.0 for k in usable}
    my, sy = statistics.fmean(y), statistics.pstdev(y) or 1.0
    lam = float(_clean(rc["calibration"])["ridge"])
    prior = float(_clean(rc["calibration"])["prior_cards"])

    def fit(rows_idx: List[int]) -> Dict[str, float]:
        if not usable:
            return dict(old)
        X = [[(feats[i].get(k, means[k]) - means[k]) / sds[k] for k in usable] for i in rows_idx]
        yy = [(y[i] - my) / sy for i in rows_idx]
        beta = _ridge(X, yy, lam)
        raw = {k: max(0.0, b / sds[k]) for k, b in zip(usable, beta)}
        tot = sum(raw.values())
        if tot <= 0:
            return dict(old)
        # features without data keep their current weight; the rest is shared by the fit
        room = sum(old[k] for k in usable)
        fitted = {k: (raw[k] / tot * room if k in usable else old[k]) for k in keys}
        share = len(rows_idx) / (len(rows_idx) + prior)
        mixed = {k: share * fitted[k] + (1 - share) * old[k] for k in keys}
        s = sum(mixed.values())
        return {k: round(v / s, 3) for k, v in mixed.items()}

    new = fit(list(range(n)))
    loo = []
    for i in range(n):
        w = fit([j for j in range(n) if j != i])
        loo.append(score(feats[i], w)[0] or 0)
    corr_loo = spearman(loo, y) if n >= 4 else None
    # Only move the weights when the new ones order unseen cards better than today's
    min_gain = float(_clean(rc["calibration"]).get("min_gain", 0.02))
    kept = corr_loo is None or corr_now is None or corr_loo < corr_now + min_gain
    return {
        "n": n, "corr": corr, "corr_ovr": corr_ovr, "corr_now": corr_now,
        "corr_new_loo": corr_loo, "old": old, "new": dict(old) if kept else new, "kept": kept,
    }


def save_calibration(new: Dict[str, float], n: int, config_dir: Path) -> Path:
    path = Path(config_dir) / CALIBRATION_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"weights": new, "cards": n, "date": datetime.now().isoformat(timespec="seconds"),
                   "_info": "Laget av 'kalibrer'. Slett filen for å gå tilbake til vektene i weights.json."},
                  f, ensure_ascii=False, indent=2)
    return path
