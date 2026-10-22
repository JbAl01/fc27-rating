"""Matchup: an attacker against a defender, duel by duel (owner 20.10).

Each card gets a profile on the attribute scale for the duels that decide whether a striker gets free or a
centre back holds on to him. The attacker's and the defender's numbers in a duel are built so they can be
compared: the gap is the advantage.

  fart  (speed race)     Acceleration and Sprint Speed, the same formula for both. AcceleRATE is shown.
  fri   (getting free)   attacker Att. Position, Reactions, Acceleration  vs  defender Def. Awareness,
                         Reactions, Interceptions (reading the run).
  kamp  (physical duel)  attacker Strength and Balance (stays on his feet)  vs  defender Strength,
                         Aggression (EA: how often and how hard he goes into challenges) and Balance.
  1v1   (on the ball)    attacker feel with the ball (feel score + body points)  vs  defender Standing
                         Tackle, Def. Awareness, Agility, Acceleration, Reactions.
  luft  (aerial duel)    Heading Accuracy, Jumping, Strength and real height, the same formula for both.

PlayStyles that act in a duel add a little (config/weights.json "matchup"). Cards are rated as they are and,
when Evo Lab has a plan with the evos out now, after that plan, so an OP evo shows up at once.
This is a view of its own and does not change IGR.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .model import _clean, group_label, rate
from .schema import Player

ATT_GROUPS = ("ST", "W", "CAM")
DEF_GROUPS = ("CB", "FB", "CDM")
AXES = ("fart", "fri", "kamp", "1v1", "luft")

DEFAULTS = {
    "fart": {"acceleration": 0.5, "sprint_speed": 0.5},
    "fri_att": {"positioning": 0.6, "reactions": 0.25, "acceleration": 0.15},
    "fri_def": {"def_awareness": 0.55, "reactions": 0.25, "interceptions": 0.2},
    "kamp_att": {"strength": 0.6, "balance": 0.4},
    "kamp_def": {"strength": 0.55, "aggression": 0.3, "balance": 0.15},
    "1v1_def": {"standing_tackle": 0.4, "def_awareness": 0.2, "agility": 0.2, "acceleration": 0.1, "reactions": 0.1},
    "luft": {"heading_accuracy": 0.4, "jumping": 0.35, "strength": 0.25},
    "height": {"ref_cm": 182, "per_cm": 0.6, "max": 8},
    "ps_att": {"Rapid": ["fart", 1.0, 2.0], "Quick Step": ["fart", 0.5, 1.0], "Enforcer": ["kamp", 1.5, 3.0],
               "Bruiser": ["kamp", 1.0, 2.0], "Technical": ["1v1", 1.0, 2.0], "Press Proven": ["1v1", 0.5, 1.0],
               "Precision Header": ["luft", 1.0, 2.0], "Aerial Fortress": ["luft", 1.5, 3.0]},
    "ps_def": {"Bruiser": ["kamp", 1.0, 2.0], "Jockey": ["1v1", 1.0, 2.0], "Anticipate": ["1v1", 1.0, 2.0],
               "Intercept": ["fri", 1.0, 2.0], "Aerial Fortress": ["luft", 1.5, 3.0], "Rapid": ["fart", 1.0, 2.0],
               "Quick Step": ["fart", 0.5, 1.0]},
    # 22.10, tested against the cards the pros and the FUT.GG teams use (both sides, the same duel): 1 v 1 and
    # speed decide most, the physical duel and the air less (used defenders top 3.35 -> 2.63 %, attackers 3.24 -> 2.62 %)
    "weights": {"fart": 0.3, "fri": 0.25, "1v1": 0.3, "kamp": 0.1, "luft": 0.05},
    "even": 1.5, "clear": 4.0,
    "cap": 8.0,   # in the total a duel counts at most this much: a clear win counts in full, one duel never decides alone
}


def settings(cfg: dict) -> dict:
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    s["_bcfg"] = cfg["weights"].get("body_profile")   # the owner's reputations, unscaled, for the defender's 1 v 1
    for k, v in _clean(cfg["weights"].get("matchup") or {}).items():
        s[k] = _clean(v) if isinstance(v, dict) else v
    return s


def _w(attrs: Dict[str, float], wts: Dict[str, float]) -> Optional[float]:
    have = {k: v for k, v in wts.items() if attrs.get(k) is not None}
    tot = sum(have.values())
    return sum(attrs[k] * v for k, v in have.items()) / tot if tot else None


def _ps(names_base, names_plus, table: dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for n in names_base:
        if n in table:
            ax, b, _ = table[n]
            out[ax] = out.get(ax, 0.0) + b
    for n in names_plus:
        if n in table:
            ax, _, p = table[n]
            out[ax] = out.get(ax, 0.0) + p
    return out


def profile(p: Player, r: dict, side: str, s: dict) -> Optional[List[float]]:
    """[fart, fri, kamp, 1v1, luft] for one side ('att' or 'def'), or None."""
    a = r.get("attributes") or p.attributes or {}
    g = r.get("position_group")
    e = r["by_group"].get(g) or {}
    hc = s["height"]
    h_adj = 0.0
    if p.height_cm:
        h_adj = max(-hc["max"], min(hc["max"], (p.height_cm - hc["ref_cm"]) * hc["per_cm"]))
    luft = _w(a, s["luft"])
    vals = {"fart": _w(a, s["fart"]), "luft": None if luft is None else luft + h_adj}
    if side == "att":
        vals["fri"] = _w(a, s["fri_att"])
        vals["kamp"] = _w(a, s["kamp_att"])
        feel = r.get("feel")
        vals["1v1"] = None if feel is None else feel + (e.get("body") or 0.0)
        bonus = _ps(p.playstyles, p.playstyles_plus, s["ps_att"])
    else:
        vals["fri"] = _w(a, s["fri_def"])
        vals["kamp"] = _w(a, s["kamp_def"])
        vals["1v1"] = _w(a, s["1v1_def"])
        from .body import reputation
        rep = reputation(p, (s.get("_bcfg") or {})) if s.get("_bcfg") else 0.0
        if vals["1v1"] is not None and rep:
            vals["1v1"] += rep   # a body known to play better than its numbers (owner: Carreras) also defends better
        bonus = _ps(p.playstyles, p.playstyles_plus, s["ps_def"])
    if any(vals[k] is None for k in AXES):
        return None
    return [round(vals[k] + bonus.get(k, 0.0), 1) for k in AXES]


def duel(att: List[float], dfn: List[float], s: dict) -> dict:
    """Gap per duel (attacker minus defender) and the weighted total. Same maths as the page."""
    gaps = [round(x - y, 1) for x, y in zip(att, dfn)]
    w, cap = s["weights"], s["cap"]
    total = round(sum(max(-cap, min(cap, gaps[i])) * w[k] for i, k in enumerate(AXES)) / sum(w.values()), 1)
    return {"gaps": gaps, "total": total}


def _row(p: Player, r: dict, side: str, s: dict, intern, evo: Optional[dict] = None) -> Optional[list]:
    prof = profile(p, r, side, s)
    if prof is None:
        return None
    g = r.get("position_group")
    e = r["by_group"].get(g) or {}
    u = r.get("usage") or {}
    used = 0 if evo else round(sum(v[0] or 0 for k, v in u.items() if k in ("pro", "com") and v), 1)
    return [intern(r["name"]), intern((r.get("rarity") or "").replace("FC 27 ", "")), r.get("ovr"), group_label(g),
            e.get("igr"), intern(r.get("accelerate") or ""), prof, intern(p.uid), evo, used]


def build(players: List[Player], results: List[dict], cfg: dict, summary: Optional[Dict[str, dict]] = None,
          lab: Optional[dict] = None) -> dict:
    """The page data: attackers and defenders, each as they are and after their best evo plan now."""
    s = settings(cfg)
    strings: List[str] = []
    index: Dict[str, int] = {}

    def intern(t: str) -> int:
        if t not in index:
            index[t] = len(strings)
            strings.append(t)
        return index[t]

    by_uid = {p.uid: p for p in players}
    att, dfn = [], []
    for r in results:
        if r.get("status") == "lekket":
            continue
        p = by_uid.get(r["uid"])
        g = r.get("position_group")
        if p is None or g not in r["by_group"]:
            continue
        side = "att" if g in ATT_GROUPS else "def" if g in DEF_GROUPS else None
        if side:
            row = _row(p, r, side, s, intern)
            if row:
                (att if side == "att" else dfn).append(row)
    n_evo = 0
    if summary and lab:
        from .evolab import _apply_delta, state_from, to_player
        rules = lab["rules"]
        by_r = {r["uid"]: r for r in results}
        for uid, sm in summary.items():
            live = sm.get("live") or {}
            if not live.get("steps") or not live.get("ld"):
                continue
            p, r0 = by_uid.get(uid), by_r.get(uid)
            if p is None or r0 is None or r0.get("status") == "lekket":
                continue
            g = r0.get("position_group")
            side = "att" if g in ATT_GROUPS else "def" if g in DEF_GROUPS else None
            if not side:
                continue
            pe = to_player(p, _apply_delta(state_from(p), live["ld"]), rules, cfg)
            re_ = rate(pe, cfg, groups=[g])
            re_["position_group"], re_["uid"] = g, uid
            if g not in re_["by_group"] or re_["by_group"][g]["igr"] <= r0["by_group"][g]["igr"] + 0.5:
                continue   # the plan must make the card better
            steps = [st["name"] for st in live["steps"]]
            row = _row(pe, re_, side, s, intern, evo=[intern(x) for x in steps])
            if row:
                (att if side == "att" else dfn).append(row)
                n_evo += 1
    return {"att": att, "def": dfn, "strings": strings, "n_evo": n_evo,
            "s": {"w": [s["weights"][k] for k in AXES], "even": s["even"], "clear": s["clear"], "cap": s["cap"]}}


_HTML = (Path(__file__).resolve().parent / "matchup_page.html").read_text(encoding="utf-8")


def render(data: dict) -> str:
    from .report import PAGE_CSS

    def dump(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    stamp = html.escape(datetime.now().strftime("%d.%m.%Y kl. %H:%M"))
    return _HTML.replace("__CSS__", PAGE_CSS).replace("__DATA__", dump(data)).replace("__STAMP__", stamp)


def write(players: List[Player], results: List[dict], cfg: dict, out_dir: str,
          summary: Optional[Dict[str, dict]] = None, lab: Optional[dict] = None) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "matchup.html"
    data = build(players, results, cfg, summary, lab)
    path.write_text(render(data), encoding="utf-8")
    print(f"Matchup: {len(data['att'])} angripere og {len(data['def'])} forsvarere ({data['n_evo']} etter evo) i {path}")
    return str(path)
