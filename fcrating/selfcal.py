"""Selvkalibrering: the model adjusts itself to what people actually play.

Every run (cmd_rate) compares our ranking with FUT.GG 'Most Used Players' (the pros' FUT squads and
the FUT.GG community's squads, equal weight) and saves two adjustments in data/cache/kalibrering.json.
The next run reads them in load_config, so the Players page, Evo Lab (Python and the page) and the
explanations all use the same numbers.

1. Body type (body_profile.learned): for each body type and position family, how many IGR points the
   cards with that body would need for the model to predict who is played. Fitted as a logistic model
   per position and source (chance of being used given IGR) with one offset per body type (shared, plus
   a smaller one per family), on one card per player and position (the best version), on the IGR
   without earlier learned points. Offsets shrink toward 0 when few cards back them, are centred so
   known bodies as a whole do not move against cards without a body type, and only HALF is applied:
   the hypothesis (research and the owner's feel) and the data weigh 50/50.
2. Position level (position_calibration.offsets): median IGR - OVR = 0 per position, as
   'kalibrer-posisjon' did by hand.

Both are smoothed over runs and only change when the change is large enough, so the pages (and the
Evo Lab cache) do not move on noise.
"""
from __future__ import annotations

import collections
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "cache" / "kalibrering.json"
FAMILY = {"ST": "atk", "W": "atk", "CAM": "atk", "CM": "mid", "CDM": "mid", "FB": "mid", "CB": "def"}
FAMILY_NO = {"atk": "angrep", "mid": "midtbane og back", "def": "midtstopper"}
USAGE_GROUP = {"ST": "ST", "CF": "ST", "LW": "W", "RW": "W", "LM": "W", "RM": "W", "CAM": "CAM", "CM": "CM",
               "CDM": "CDM", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "CB": "CB", "GK": "GK"}
DEFAULTS = {"share": 0.5, "sd_frame": 1.0, "sd_family": 0.6, "min_used": 4, "max_abs": 1.0, "smooth": 0.3,
            "step": 0.2, "pos_step": 0.3, "iterations": 40}


def _settings(cfg: dict) -> dict:
    s = dict(DEFAULTS)
    s.update({k: v for k, v in ((cfg["weights"].get("self_calibration") or {}).items()) if not k.startswith("_")})
    return s


def load(path: Path = PATH) -> Optional[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def apply(cfg: dict, data: Optional[dict] = None) -> None:
    """Put the saved adjustments into the config (load_config calls this)."""
    data = data if data is not None else load()
    if not data:
        return
    w = cfg["weights"]
    if data.get("body") and w.get("body_profile") and data.get("model") == model_signature(cfg):   # not learned on an old model
        w["body_profile"]["learned"] = data["body"]
    if data.get("pos") and w.get("position_calibration"):
        w["position_calibration"]["offsets"] = dict(data["pos"])


def frame_key(fr: Optional[dict]) -> Optional[str]:
    if not fr:
        return None
    return "unique" if fr["unique"] else f"{fr['build']}_{fr['size']}"


def learned_points(bcfg: dict, group: str, fr: Optional[dict]) -> float:
    """The learned points for this body in this position (0 if none)."""
    fam, key = FAMILY.get(group), frame_key(fr)
    if not fam or not key:
        return 0.0
    return float(((bcfg.get("learned") or {}).get(fam) or {}).get(key, 0.0))


# ---------------------------------------------------------------- body fit

def _player_key(r: dict) -> Tuple:
    return (r.get("name"), r.get("nation"), r.get("gender"))


def _rows(results: List[dict]) -> List[Tuple[str, str, float, List[int]]]:
    """One row per player and position: (group, body, IGR without learned points, [used by pros, used by community]).
    Only cards with a body type read from FUT.GG (not estimated) and not leaked."""
    best: Dict[Tuple, list] = {}
    for r in results:
        if r.get("status") == "lekket":
            continue
        u = r.get("usage") or {}
        for g, e in r["by_group"].items():
            bd = e.get("body_detail")
            if g not in FAMILY or not bd or bd.get("estimated") or not bd.get("key"):
                continue
            used = [1 if (u.get(s) and USAGE_GROUP.get(u[s][1]) == g) else 0 for s in ("pro", "com")]
            x = e["igr"] - (bd.get("learn") or 0.0)
            k = _player_key(r) + (g,)
            cur = best.get(k)
            if cur is None:
                best[k] = [g, bd["key"], x, used]
            else:
                if x > cur[2]:
                    cur[1], cur[2] = bd["key"], x
                cur[3] = [max(a, b) for a, b in zip(cur[3], used)]
    return [tuple(v) for v in best.values()]


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def fit_body(rows, s: dict) -> Tuple[Dict[str, Dict[str, float]], Dict[str, int]]:
    """{family: {body: points}} the data asks for (before the 50/50 share), and how many used players per body."""
    groups = sorted({g for g, _, _, _ in rows})
    frames = sorted({f for _, f, _, _ in rows})
    fams = sorted({FAMILY[g] for g in groups})
    used_n = collections.Counter(f for _, f, _, u in rows if any(u))
    if not rows or sum(used_n.values()) < 10:
        return {}, dict(used_n)
    d1 = {f: 0.0 for f in frames}
    d2 = {(f, m): 0.0 for f in frames for m in fams}
    ab = {(g, src): [0.0, 0.3] for g in groups for src in (0, 1)}
    top = {g: max(x for gg, _, x, _ in rows if gg == g) for g in groups}
    by_g = collections.defaultdict(list)
    for row in rows:
        by_g[row[0]].append(row)

    def off(g, f):
        return d1[f] + d2[(f, FAMILY[g])]

    for _ in range(int(s["iterations"])):
        for (g, src), p in ab.items():
            h00 = h01 = h11 = 1e-6
            g0 = g1 = 0.0
            for _, f, x, u in by_g[g]:
                z = x + off(g, f) - top[g]
                pr = _sig(p[0] + p[1] * z)
                e, w = u[src] - pr, pr * (1 - pr)
                g0 += e
                g1 += e * z
                h00 += w
                h01 += w * z
                h11 += w * z * z
            det = h00 * h11 - h01 * h01
            if det > 0:
                p[0] += (h11 * g0 - h01 * g1) / det
                p[1] += (-h01 * g0 + h00 * g1) / det
                p[1] = max(0.01, p[1])
        for level, D, sd in ((1, d1, s["sd_frame"]), (2, d2, s["sd_family"])):
            gr, hs = collections.Counter(), collections.Counter()
            for g, f, x, u in rows:
                k = f if level == 1 else (f, FAMILY[g])
                for src in (0, 1):
                    a, b = ab[(g, src)]
                    pr = _sig(a + b * (x + off(g, f) - top[g]))
                    gr[k] += (u[src] - pr) * b
                    hs[k] += pr * (1 - pr) * b * b
            for k in D:
                D[k] += (gr[k] - D[k] / sd ** 2) / (hs[k] + 1 / sd ** 2)
    out: Dict[str, Dict[str, float]] = {}
    for m in fams:
        pop = [f for g, f, _, _ in rows if FAMILY[g] == m]
        mean = sum(d1[f] + d2[(f, m)] for f in pop) / len(pop)
        out[m] = {f: round(d1[f] + d2[(f, m)] - mean, 2) for f in frames
                  if used_n[f] >= s["min_used"]}   # too few played cards with this body: no opinion
    return out, dict(used_n)


# ---------------------------------------------------------------- positions

def fit_positions(results: List[dict]) -> Dict[str, float]:
    from .schema import position_group
    diffs: Dict[str, List[float]] = {}
    for r in results:
        g = position_group(r.get("position"))
        e = r["by_group"].get(g or "")
        if not e or r.get("status") == "lekket" or not r.get("ovr"):
            continue
        diffs.setdefault(g, []).append(e["igr"] - (e.get("calibration") or 0.0) - r["ovr"])
    return {g: round(-statistics.median(v), 1) for g, v in diffs.items() if len(v) >= 30}


# ---------------------------------------------------------------- update

def model_signature(cfg: dict) -> str:
    """The model the adjustments were learned on (everything but the adjustments themselves). When the model
    changes, the old adjustments are thrown away: they corrected the old model, not this one."""
    import copy
    import hashlib
    w = copy.deepcopy(cfg["weights"])
    bp = w.get("body_profile") or {}
    for k in ("learned", "rep_frames"):
        bp.pop(k, None)
    (w.get("position_calibration") or {}).pop("offsets", None)
    w.pop("self_calibration", None)
    return hashlib.sha1(json.dumps([w, cfg.get("playstyles")], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def update(results: List[dict], cfg: dict, path: Path = PATH, log=print) -> Optional[dict]:
    """Fit, smooth, save (only when something moved enough). Used from the next run on."""
    s = _settings(cfg)
    old = load(path) or {}
    sig = model_signature(cfg)
    fresh = old.get("model") != sig
    if fresh and old:
        log("Selvkalibrering: modellen er endret siden sist, så de gamle justeringene er forkastet og læres på nytt.")
        old = {"pos": old.get("pos")}
    rows = _rows(results)
    raw, used_n = fit_body(rows, s)
    smooth_old = old.get("body_raw") or {}
    smooth = {}
    for m, fr in raw.items():
        smooth[m] = {}
        for f, v in fr.items():
            prev = (smooth_old.get(m) or {}).get(f)
            smooth[m][f] = round(v if prev is None else prev + s["smooth"] * (v - prev), 2)
    body = {m: {f: round(max(-s["max_abs"], min(s["max_abs"], s["share"] * v)), 1) for f, v in fr.items()}
            for m, fr in smooth.items()}
    body = {m: {f: v for f, v in fr.items() if v} for m, fr in body.items()}
    old_body = old.get("body") or {}
    moved = max([abs(body.get(m, {}).get(f, 0.0) - old_body.get(m, {}).get(f, 0.0))
                 for m in set(body) | set(old_body)
                 for f in set(body.get(m, {})) | set(old_body.get(m, {}))] or [0.0])
    new_body = body if moved >= s["step"] else old_body

    pos = fit_positions(results)
    old_pos = old.get("pos") or dict(((cfg["weights"].get("position_calibration") or {}).get("offsets")) or {})
    pos_moved = max([abs(pos.get(g, 0.0) - old_pos.get(g, 0.0)) for g in pos] or [0.0])
    new_pos = pos if pos and (pos_moved >= s["pos_step"] or fresh) else old_pos

    data = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "model": sig, "body": new_body, "body_raw": smooth,
            "body_used": used_n, "pos": new_pos, "rows": len(rows)}
    if new_body != old_body or new_pos != (old.get("pos") or {}) or not path.exists():
        data["changed"] = data["t"]
    else:
        data["changed"] = old.get("changed")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    shown = "; ".join(f"{FAMILY_NO[m]}: " + ", ".join(f"{f} {v:+.1f}" for f, v in sorted(fr.items(), key=lambda t: -t[1]))
                      for m, fr in sorted(new_body.items()) if fr)
    log(f"Selvkalibrering: {len(rows)} spillere med kroppstype, {sum(used_n.values())} av dem spilles. "
        f"Kropp (halve datautslaget): {shown or 'ingen endring ennå'}"
        + ("" if new_body == old_body else " [ny]")
        + f". Posisjonsnivå: " + ", ".join(f"{g} {v:+.1f}" for g, v in new_pos.items())
        + ("" if new_pos == old_pos else " [ny]") + ". Brukes fra neste kjøring.")
    return data


# ---------------------------------------------------------------- test list for the owner

def test_list(results: List[dict], limit: int = 12) -> List[str]:
    """Where the model and the players disagree most: cards many play that we rank low, and common
    gold cards in our top 1 % that nobody plays (no version of the player is used). The owner tests
    these in game instead of guessing. Lines of plain text."""
    used_players = {_player_key(r) for r in results if r.get("usage")}
    low, high = [], []
    for r in results:
        if r.get("status") == "lekket":
            continue
        u = r.get("usage") or {}
        for src, who in (("pro", "proffene"), ("com", "FUT.GG-lagene")):
            if not u.get(src):
                continue
            pct, pos = u[src]
            g = USAGE_GROUP.get(pos)
            e = r["by_group"].get(g or "")
            if e and e.get("top_pct") is not None and e["top_pct"] > 5:
                low.append((e["top_pct"], f"{r['name']} ({r.get('rarity') or ''}, {r.get('ovr')}) {pos}: {pct:g} % av "
                                          f"{who} bruker kortet, hos oss topp {e['top_pct']:g} % i {g}"))
        rar = (r.get("rarity") or "").lower()
        if _player_key(r) in used_players or not (rar.endswith("rare gold") or rar == "fc 27 gold"):
            continue
        g = r.get("position_group")
        e = r["by_group"].get(g or "")
        if e and e.get("top_pct") is not None and e["top_pct"] <= 1.0 and g != "GK":
            high.append((e["top_pct"], f"{r['name']} ({r.get('rarity')}, {r.get('ovr')}) {g}: topp {e['top_pct']:g} % hos oss, "
                                       f"men ingen bruker kortet"))
    low.sort(key=lambda t: -t[0])
    high.sort(key=lambda t: t[0])
    seen, lines = set(), []
    for _, t in low:
        if t not in seen:
            seen.add(t)
            lines.append(t)
    out = ["Spilles mye, men rangeres lavt hos oss (test om de føles bedre enn tallet):"]
    out += ["  " + t for t in lines[:limit]] or ["  ingen"]
    out += ["", "Rangeres høyt hos oss, men ingen spiller dem (test om de føles så gode som tallet):"]
    out += ["  " + t for _, t in high[:limit]] or ["  ingen"]
    return out
