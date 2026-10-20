"""Own in-game rating (IGR) and evo potential for FC 27 players.

IGR for a position group =
    blend.feel  * Feel      (how quick and responsive the player feels)
  + blend.pace  * Pace      (effective pace, acceleration-weighted)
  + blend.skill * Skill     (position-specific attributes)
  + blend.run   * Løps-AI   (movement without the ball; ST, W and CAM only)
  + PlayStyle bonus         (scaled by position relevance and attribute synergy)
  + role bonus              (+ / ++ familiarity)
  + weak foot / skill moves bonus

All weights come from config/*.json.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import accelerate as acc_mod
from .schema import GROUP_LABELS_NO, OUTFIELD_ATTRIBUTES, Player

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
ALL_GROUPS = ["ST", "W", "CAM", "CM", "CDM", "FB", "CB", "GK"]


def load_config(config_dir: Optional[Path] = None) -> dict:
    d = Path(config_dir) if config_dir else CONFIG_DIR
    with open(d / "weights.json", encoding="utf-8") as f:
        weights = json.load(f)
    with open(d / "playstyles.json", encoding="utf-8") as f:
        playstyles = json.load(f)
    with open(d / "chem_styles.json", encoding="utf-8") as f:
        chem = json.load(f)
    cfg = {"weights": weights, "playstyles": playstyles, "chem": chem}
    if "run_ai" in weights:
        from .runs import load_calibration
        load_calibration(cfg, d)
    if config_dir is None:   # the adjustments learned from what people play (data/cache/kalibrering.json)
        from .selfcal import apply as apply_selfcal
        apply_selfcal(cfg)
    return cfg


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if not str(k).startswith("_")}


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def weighted(attrs: Dict[str, float], weights: Dict[str, float]) -> Tuple[Optional[float], float]:
    """Weighted average over present attributes. Returns (score, completeness 0-1)."""
    w = _clean(weights)
    total = sum(w.values())
    present = {k: v for k, v in w.items() if k in attrs}
    got = sum(present.values())
    if got <= 0:
        return None, 0.0
    score = sum(attrs[k] * v for k, v in present.items()) / got
    return score, got / total if total else 0.0


# ---------------------------------------------------------------- chemistry

def chem_boost_at_level(boost: float, level: int) -> int:
    if level >= 3:
        return int(boost)
    if level <= 0:
        return 0
    return int(round(boost * level / 3.0))


def apply_chem(attrs: Dict[str, float], style: Optional[str], chem_cfg: dict,
               level: int = 3) -> Dict[str, float]:
    if not style:
        return dict(attrs)
    entry = chem_cfg["styles"].get(style)
    if not entry or not entry.get("boosts"):
        raise ValueError(f"Kjemistilen '{style}' har ingen boosts i config/chem_styles.json")
    out = dict(attrs)
    for key, boost in entry["boosts"].items():
        if key in out:
            out[key] = min(99.0, out[key] + chem_boost_at_level(boost, level))
    return out


def known_chem_styles(chem_cfg: dict) -> List[str]:
    return [name for name, e in chem_cfg["styles"].items() if e.get("boosts")]


# ---------------------------------------------------------------- components

def effective_height(player: Player, hcfg: dict) -> Optional[float]:
    if player.height_cm is None:
        return None
    return player.height_cm + (hcfg["female_offset_cm"] if player.gender == "F" else 0)


def height_adjust(player: Player, hcfg: dict, lean: bool = False) -> float:
    """lean: the card has a Lean body (known or worked out from height and weight). Lean bodies move
    better than their height says (owner's experience, Lean Tall with Technical+; FUT.GG and SI on tall
    lean players), so they get only part of the penalty for height (lean_penalty_factor)."""
    h = effective_height(player, hcfg)
    if h is None:
        return 0.0
    adj = 0.0
    if h > hcfg["neutral_cm"]:
        adj -= (h - hcfg["neutral_cm"]) * hcfg["penalty_per_cm_above"] * (hcfg.get("lean_penalty_factor", 1.0) if lean else 1.0)
    if h < hcfg["short_cm"]:
        adj += (hcfg["short_cm"] - h) * hcfg["bonus_per_cm_below"]
    return clamp(adj, hcfg["min_adjust"], hcfg["max_adjust"])


def body_type_adjust(player: Player, bcfg: dict) -> float:
    bt = (player.body_type or "").lower()
    if not bt:
        return 0.0
    adj = 0.0
    if "lean" in bt:
        adj += bcfg.get("lean", 0.0)
    if "stocky" in bt:
        adj += bcfg.get("stocky", 0.0)
    return adj


def accelerate_type(player: Player, attrs: Dict[str, float], wcfg: dict,
                    chem_applied: bool) -> Tuple[Optional[str], str]:
    acc_type, reason = acc_mod.classify(attrs, player.height_cm, player.gender, wcfg["accelerate_rules"])
    if acc_type is None and player.accelerate_source and not chem_applied:
        return player.accelerate_source, f"fra datakilden ({reason})"
    return acc_type, reason


def feel_score(player: Player, attrs: Dict[str, float], acc_type: Optional[str],
               wcfg: dict) -> Tuple[Optional[float], dict]:
    fcfg = wcfg["feel"]
    base, completeness = weighted(attrs, fcfg["attributes"])
    if base is None:
        return None, {"completeness": 0.0}
    from .body import is_lean
    h_adj = height_adjust(player, fcfg["height"], is_lean(player, wcfg.get("body_profile")))
    a_adj = fcfg["accelerate"].get(acc_type or "", 0.0)
    b_adj = body_type_adjust(player, fcfg["body_type"])
    return base + h_adj + a_adj + b_adj, {
        "attributes": round(base, 1), "height": round(h_adj, 2),
        "accelerate": a_adj, "body_type": b_adj, "completeness": round(completeness, 2),
    }


def pace_score(attrs: Dict[str, float], group: str, acc_type: Optional[str],
               wcfg: dict) -> Optional[float]:
    pcfg = wcfg["pace"]
    share = pcfg["acceleration_share"].get(group, pcfg["acceleration_share"]["default"])
    a, s = attrs.get("acceleration"), attrs.get("sprint_speed")
    if a is None and s is None:
        return None
    if a is None:
        a = s
    if s is None:
        s = a
    return share * a + (1 - share) * s + pcfg["accelerate"].get(acc_type or "", 0.0)


def skill_score(attrs: Dict[str, float], group: str, wcfg: dict) -> Tuple[Optional[float], float]:
    return weighted(attrs, wcfg["skill"][group])


def synergy(attrs: Dict[str, float], keys: List[str], scfg: dict) -> float:
    vals = [attrs[k] for k in keys if k in attrs]
    if not vals:
        return 0.6  # unknown attributes: neutral-ish
    avg = sum(vals) / len(vals)
    return clamp((avg - scfg["floor"]) / scfg["span"], scfg["min"], scfg["max"])


def playstyle_bonus(player: Player, attrs: Dict[str, float], group: str,
                    ps_cfg: dict) -> Tuple[float, List[dict]]:
    table = ps_cfg["playstyles"]
    rel_cat = ps_cfg["category_relevance"]
    items: List[dict] = []
    for name, is_plus in [(p, True) for p in player.playstyles_plus] + [(p, False) for p in player.playstyles]:
        entry = table.get(name)
        if not entry:
            continue
        value = entry["plus" if is_plus else "base"]
        relevance = (entry.get("relevance") or rel_cat[entry["category"]]).get(group, 0.0)
        syn = synergy(attrs, entry.get("synergy", []), ps_cfg["synergy"])
        damp = 1.0
        dcfg = entry.get("dampen")
        if dcfg and dcfg["attribute"] in attrs:
            # the attribute alone already gives much of the effect (e.g. high Interceptions in FC 27)
            t = clamp((attrs[dcfg["attribute"]] - dcfg["from"]) / (dcfg["to"] - dcfg["from"]), 0.0, 1.0)
            damp = 1.0 - (1.0 - dcfg["min_factor"]) * t
        items.append({
            "name": name + ("+" if is_plus else ""),
            "value": value, "relevance": relevance, "synergy": round(syn, 2),
            "raw": value * relevance * syn * damp,
        })
    items.sort(key=lambda x: x["raw"], reverse=True)
    factors = ps_cfg["diminishing"]["factors"]
    total = 0.0
    for i, it in enumerate(items):
        f = factors[i] if i < len(factors) else factors[-1]
        it["points"] = round(it["raw"] * f, 2)
        total += it["raw"] * f
    return min(total, ps_cfg["diminishing"]["max_total"]), items


def role_bonus(player: Player, group: str, wcfg: dict) -> Tuple[float, Optional[str]]:
    rcfg = wcfg["roles"]
    best_level, best_name = -1, None
    for pos in rcfg["group_positions"].get(group, []):
        for role, level in (player.roles.get(pos) or {}).items():
            if level > best_level:
                best_level, best_name = level, f"{role}{'+' * level} ({pos})"
    if best_level < 0:
        return 0.0, None
    return rcfg["points"].get(str(best_level), 0.0), best_name


def foot_bonus(player: Player, group: str, wcfg: dict) -> Tuple[float, float]:
    wf_cfg, sm_cfg = wcfg["weak_foot"], wcfg["skill_moves"]
    wf = 0.0
    if player.weak_foot is not None:
        wf = wf_cfg["points"].get(str(player.weak_foot), 0.0) * wf_cfg["group_factor"].get(group, 0.0)
    sm = 0.0
    if player.skill_moves is not None:
        sm = sm_cfg["points"].get(str(player.skill_moves), 0.0) * sm_cfg["group_factor"].get(group, 0.0)
    return wf, sm


def gk_height_adjust(player: Player, wcfg: dict) -> float:
    g = wcfg["gk_height"]
    if player.height_cm is None:
        return 0.0
    offset = g.get("female_offset_cm", wcfg["feel"]["height"]["female_offset_cm"])
    h = player.height_cm + (offset if player.gender == "F" else 0)
    if h >= g["neutral_cm"]:
        adj = (h - g["neutral_cm"]) * g["bonus_per_cm_above"]
    else:
        adj = -(g["neutral_cm"] - h) * g["penalty_per_cm_below"]
    return clamp(adj, g["min_adjust"], g["max_adjust"])


def tier_for(igr: float, wcfg: dict) -> str:
    tiers = sorted(_clean(wcfg["tiers"]).items(), key=lambda kv: kv[1], reverse=True)
    for letter, threshold in tiers:
        if igr >= threshold:
            return letter
    return tiers[-1][0]


# ---------------------------------------------------------------- rating

def off_balance_bonus(obd: Optional[float], group: str, wcfg: dict) -> float:
    c = wcfg.get("off_balance")
    if not c or obd is None:
        return 0.0
    pts = clamp((obd - c["start"]) * c["per_point"], 0.0, c["max"])
    return pts * c["group_factor"].get(group, 0.0)


def stand_tackle_bonus(attrs: Dict[str, float], group: str, wcfg: dict) -> float:
    c = wcfg.get("stand_tackle_tiers")
    st = attrs.get("standing_tackle")
    factor = (c or {}).get("group_factor", {}).get(group, 0.0)
    if not c or st is None or not factor:
        return 0.0
    pts = 0.0
    for threshold, value in c["tiers"]:
        if st >= threshold:
            pts = value
    return pts * factor


def position_offset(group: str, wcfg: dict) -> float:
    """The fixed level adjustment for the position (weights.json position_calibration)."""
    return float(((wcfg.get("position_calibration") or {}).get("offsets") or {}).get(group, 0.0))


def rate_group(player: Player, attrs: Dict[str, float], group: str, acc_type: Optional[str],
               feel: Optional[float], cfg: dict, obd: Optional[float] = None,
               run_score: Optional[float] = None, stop_score: Optional[float] = None) -> Optional[dict]:
    wcfg, ps_cfg = cfg["weights"], cfg["playstyles"]
    blend = wcfg["blend"][group]
    skill, skill_comp = skill_score(attrs, group, wcfg)
    if skill is None:
        return None
    pace = pace_score(attrs, group, acc_type, wcfg) if group != "GK" else None
    core = blend["skill"] * skill
    weight_used = blend["skill"]
    if blend["feel"] and feel is not None:
        core += blend["feel"] * feel
        weight_used += blend["feel"]
    if blend["pace"] and pace is not None:
        core += blend["pace"] * pace
        weight_used += blend["pace"]
    run_used = None
    if blend.get("run") and run_score is not None:
        core += blend["run"] * run_score
        weight_used += blend["run"]
        run_used = run_score
    stop_used = None
    if blend.get("stop") and stop_score is not None:
        core += blend["stop"] * stop_score
        weight_used += blend["stop"]
        stop_used = stop_score
    core = core / weight_used  # renormalize if feel or pace is missing

    ps_pts, ps_items = playstyle_bonus(player, attrs, group, ps_cfg)
    role_pts, role_name = role_bonus(player, group, wcfg)
    wf_pts, sm_pts = foot_bonus(player, group, wcfg)
    gk_adj = gk_height_adjust(player, wcfg) if group == "GK" else 0.0

    ob_pts = off_balance_bonus(obd, group, wcfg)
    st_pts = stand_tackle_bonus(attrs, group, wcfg)
    from .body import BodyCard
    bc = BodyCard(player, group, wcfg.get("body_profile"))
    body = bc.detail(attrs, player.playstyles, player.playstyles_plus)
    body_pts = bc.points(attrs, player.playstyles, player.playstyles_plus) if body else 0.0

    cal = position_offset(group, wcfg)
    igr = core + ps_pts + role_pts + wf_pts + sm_pts + gk_adj + ob_pts + st_pts + body_pts + cal
    return {
        "group": group,
        "igr": round(igr, 1),
        "tier": tier_for(igr, wcfg),
        "core": round(core, 1),
        "feel": round(feel, 1) if feel is not None else None,
        "pace": round(pace, 1) if pace is not None else None,
        "skill": round(skill, 1),
        "skill_completeness": round(skill_comp, 2),
        "playstyles": round(ps_pts, 2),
        "playstyle_details": ps_items,
        "role": role_pts,
        "role_name": role_name,
        "weak_foot": round(wf_pts, 2),
        "skill_moves": round(sm_pts, 2),
        "gk_height": round(gk_adj, 2),
        "run_score": round(run_used, 1) if run_used is not None else None,
        "stop_score": round(stop_used, 1) if stop_used is not None else None,
        "off_balance": round(ob_pts, 2),
        "stand_tackle": round(st_pts, 2),
        "body": round(body_pts, 2),
        "body_detail": body,
        "calibration": cal,
    }


def _frame_code(player: Player, wcfg: dict):
    from .body import frame_code, frame_of
    bcfg = wcfg.get("body_profile")
    return frame_code(frame_of(player, bcfg)) if bcfg else 0


def _futgg_page(player: Player) -> Optional[str]:
    from .sources.futgg import player_page
    return player_page(player)


def rate(player: Player, cfg: dict, chem: Optional[str] = None, chem_level: int = 3,
         groups: Optional[List[str]] = None) -> dict:
    """Rate one player. chem: None, a style name, or 'best' (best known style)."""
    if chem == "best":
        best = None
        for style in [None] + known_chem_styles(cfg["chem"]):
            r = rate(player, cfg, chem=style, chem_level=chem_level, groups=groups)
            if best is None or r["igr"] > best["igr"]:
                best = r
        return best

    wcfg = cfg["weights"]
    attrs = apply_chem(player.attributes, chem, cfg["chem"], chem_level)
    acc_type, acc_reason = accelerate_type(player, attrs, wcfg, chem_applied=bool(chem))
    feel, feel_parts = feel_score(player, attrs, acc_type, wcfg)
    obd = player.off_balance_dribbling if (player.off_balance_dribbling is not None and not chem) else \
        acc_mod.off_balance_dribbling(attrs, wcfg["off_balance_dribbling"]["weights"])

    from .runs import card_run_score
    run_sc = card_run_score(attrs, player.work_rate_att, player.height_cm, cfg)
    from .stop import scores as stop_scores
    from .stop import core as stop_core
    stop_igr = stop_core(attrs, acc_type, cfg) if player.position != "GK" else None   # without PlayStyles: no double counting
    stop_sc, stop_ball, stop_run = stop_scores(attrs, acc_type, player.playstyles, player.playstyles_plus, cfg) \
        if player.position != "GK" else (None, None, None)
    rate_groups = groups or player.groups or ALL_GROUPS
    by_group: Dict[str, dict] = {}
    for g in rate_groups:
        res = rate_group(player, attrs, g, acc_type, feel, cfg, obd=obd, run_score=run_sc, stop_score=stop_igr)
        if res:
            by_group[g] = res

    warnings: List[str] = []
    missing = [a for a in OUTFIELD_ATTRIBUTES if a not in player.attributes]
    if missing and player.position != "GK":
        from .schema import ATTRIBUTE_LABELS
        names = ", ".join(ATTRIBUTE_LABELS.get(a, a) for a in missing[:3])
        warnings.append(f"mangler {names}" + (f" og {len(missing) - 3} til" if len(missing) > 3 else ""))
    if player.height_cm is None:
        warnings.append("høyde mangler (påvirker følelse og AcceleRATE)")
    if not player.body_type and player.position != "GK" and wcfg.get("body_profile"):
        from .body import frame_of
        warnings.append("kroppstype ikke hentet ennå (" + ("anslått fra høyde og vekt" if frame_of(player, wcfg["body_profile"])
                                                         else "teller 0 i kroppsprofilen") + ")")
    if not player.playstyles_complete:
        warnings.append("PlayStyle-listen er ufullstendig")
    if not player.roles_complete:
        warnings.append("roller mangler")
    if acc_type and player.accelerate_source and not chem and acc_type != player.accelerate_source:
        warnings.append(f"AcceleRATE avviker fra kilden ({player.accelerate_source})")

    if player.estimated:
        warnings.append("attributter estimert fra basekort og hovedtall")
    if player.status == "lekket":
        warnings.append("lekket kort, ikke bekreftet")

    best_group = max(by_group, key=lambda g: by_group[g]["igr"]) if by_group else None
    return {
        "uid": player.uid,
        "status": player.status,
        "estimated": player.estimated,
        "url": player.url,
        "futgg": _futgg_page(player),
        "name": player.name,
        "id": player.id,
        "ovr": player.ovr,
        "position": player.position,
        "positions": [player.position] + list(player.alt_positions),
        "rarity": player.rarity,
        "club": player.club,
        "image": player.image,
        "card_image": player.card_image,
        "card_color": player.card_color,
        "club_image": player.club_image,
        "nation_image": player.nation_image,
        "league_image": player.league_image,
        "foot": (player.foot or "")[:1].upper() if (player.foot or "")[:1].upper() in ("L", "R") else "",
        "league": player.league,
        "nation": player.nation,
        "price": player.price,
        "chem_style": chem,
        "chem_level": chem_level if chem else None,
        "accelerate": acc_type,
        "accelerate_reason": acc_reason,
        "off_balance_dribbling": obd,
        "hard_to_stop": {"score": stop_sc, "ball": stop_ball, "run": stop_run} if stop_sc is not None else None,
        "feel": round(feel, 1) if feel is not None else None,
        "feel_parts": feel_parts,
        "attributes": {k: v for k, v in attrs.items() if v},
        "height_cm": player.height_cm,
        "weight_kg": player.weight_kg,
        "body_type": player.body_type,
        "frame": _frame_code(player, wcfg),
        "gender": player.gender,
        "weak_foot": player.weak_foot,
        "skill_moves": player.skill_moves,
        "work_rate_att": player.work_rate_att,
        "work_rate_def": player.work_rate_def,
        "ps_known": bool(player.playstyles_complete or player.playstyles or player.playstyles_plus),
        "by_group": by_group,
        "best_group": best_group,
        "igr": by_group[best_group]["igr"] if best_group else 0.0,
        "tier": by_group[best_group]["tier"] if best_group else None,
        "warnings": warnings,
        "source": player.source,
    }


# ---------------------------------------------------------------- position ranking

def primary_group(result: dict) -> Optional[str]:
    from .schema import position_group
    return position_group(result.get("position"))


def rank_by_position(results: List[dict], cfg: dict) -> List[dict]:
    """Rank players only against players who can play the same position.

    For every position group, the pool is everyone who has that position as
    primary or alternative position. Adds to each by_group entry:
    rank, of (pool size), top_pct and pos_tier. Adds the same for the
    player's primary position at the top level of the result.
    """
    wcfg = cfg["weights"]
    pt = wcfg.get("position_tiers", {})
    min_pool = pt.get("min_pool_size", 30)
    cutoffs = sorted(((k, v) for k, v in _clean(pt).items() if k != "min_pool_size"), key=lambda kv: kv[1])

    pools: Dict[str, List[dict]] = {}
    for r in results:
        for g in r["by_group"]:
            pools.setdefault(g, []).append(r)

    from .explain import add_explanations, impute_playstyles
    impute_playstyles(pools, cfg)

    for g, pool in pools.items():
        pool.sort(key=lambda r: r["by_group"][g]["igr"], reverse=True)
        n = len(pool)
        for i, r in enumerate(pool, 1):
            entry = r["by_group"][g]
            top_pct = round(100.0 * i / n, 1)
            if n >= min_pool:
                tier = next((k for k, v in cutoffs if top_pct <= v), cutoffs[-1][0])
                basis = "plassering"
            else:
                tier = entry["tier"]
                basis = "IGR (for få spillere i posisjonen)"
            entry.update(rank=i, of=n, top_pct=top_pct, pos_tier=tier, tier_basis=basis)

    for r in results:
        g = primary_group(r)
        if g not in r["by_group"]:
            g = r["best_group"]
        r["position_group"] = g
        entry = r["by_group"].get(g or "")
        if entry:
            r["pos_igr"] = entry["igr"]
            r["pos_rank"], r["pos_of"] = entry["rank"], entry["of"]
            r["pos_top_pct"], r["pos_tier"] = entry["top_pct"], entry["pos_tier"]
        else:
            r["pos_igr"] = r["pos_rank"] = r["pos_of"] = r["pos_top_pct"] = r["pos_tier"] = None
    add_explanations(pools, cfg)
    from .gems import add_gems
    add_gems(pools, cfg)
    if "run_ai" in wcfg:
        from .runs import add_run_ai
        add_run_ai(results, cfg)
    if "profile" in wcfg:
        from .profile import add_profile
        add_profile(results, cfg)
    return results


# ---------------------------------------------------------------- evolutions

def evo_eligibility(player: Player, ecfg: dict) -> Tuple[bool, str]:
    """Can this card realistically be used in evolutions?"""
    if player.status == "lekket" and ecfg.get("exclude_leaks", True):
        return False, "lekket kort, ikke utgitt ennå"
    version = (player.rarity or "").lower()
    for word in ecfg.get("excluded_versions", []):
        if word.lower() in version:
            return False, f"{word}-kort kan ikke evolueres"
    if player.ovr is not None and player.ovr > ecfg["max_ovr"]:
        return False, f"for høy OVR ({player.ovr} > {ecfg['max_ovr']})"
    if player.position == "GK" and not ecfg.get("include_gk", False):
        return False, "keepere er sjelden med i evoer"
    return True, "kan evolueres"


def evo_boost(player: Player, ecfg: dict) -> float:
    """Evolutions add the most to low-rated cards: points per OVR below the target."""
    if player.ovr is None:
        return float(ecfg["max_boost"]) / 2
    return clamp((ecfg["target_ovr"] - player.ovr) * ecfg["points_per_ovr"], 0, ecfg["max_boost"])


def evolved_copy(player: Player, ecfg: dict) -> Player:
    p = copy.deepcopy(player)
    cap = ecfg["attribute_cap"]
    explicit = _clean(ecfg.get("attribute_boosts") or {})
    boost = evo_boost(player, ecfg)
    for key in OUTFIELD_ATTRIBUTES:
        if key not in p.attributes:
            continue
        add = explicit.get(key, 0) if explicit else boost
        if add:
            p.attributes[key] = max(p.attributes[key], min(cap, round(p.attributes[key] + add)))
    if p.weak_foot is not None:
        p.weak_foot = max(p.weak_foot, ecfg.get("weak_foot_min", 0))
    if p.skill_moves is not None:
        p.skill_moves = max(p.skill_moves, ecfg.get("skill_moves_min", 0))
    for ps in ecfg.get("add_playstyles") or []:
        if ps not in p.playstyles and ps not in p.playstyles_plus:
            p.playstyles.append(ps)
    if p.ovr is not None:
        p.ovr = int(max(p.ovr, min(ecfg["target_ovr"], p.ovr + round(boost))))
    return p


def evo_potential(player: Player, cfg: dict, chem: Optional[str] = None) -> dict:
    ecfg = cfg["weights"]["evo"]
    now = rate(player, cfg, chem=chem)
    eligible, reason = evo_eligibility(player, ecfg)
    from .schema import position_group
    group = position_group(player.position) or now["best_group"]
    out = {
        "uid": player.uid,
        "name": player.name,
        "ovr": player.ovr,
        "position": player.position,
        "group": group,
        "eligible": eligible,
        "reason": reason,
        "igr_now": now["by_group"].get(group, {}).get("igr", now["igr"]),
        "igr_after": None, "gain": None, "evo_value": None, "boost": None,
        "best_group_after": None, "accelerate_now": now["accelerate"], "accelerate_after": None,
        "feel_after": None, "rank_now": None, "rank_after": None, "of": None, "ovr_after": None,
        "price": player.price,
    }
    if not eligible:
        return out
    evolved = evolved_copy(player, ecfg)
    after = rate(evolved, cfg, chem=chem, groups=list(now["by_group"]) or None)
    igr_after = after["by_group"].get(group, {}).get("igr", after["igr"])
    out.update(
        igr_after=igr_after,
        gain=round(igr_after - out["igr_now"], 1),
        evo_value=igr_after,
        boost=round(evo_boost(player, ecfg), 1),
        ovr_after=evolved.ovr,
        best_group_after=after["best_group"],
        accelerate_after=after["accelerate"],
        feel_after=after["feel"],
    )
    return out


def rank_evos(evos: Dict[str, dict], results: List[dict]) -> None:
    """Where would each evolved card land among today's cards in its position?

    Run after rank_by_position: the card's current IGR is taken from the ranked
    results (which include estimated PlayStyles), and the same adjustment is
    applied to the evolved IGR so before and after are comparable."""
    import bisect
    pools: Dict[str, List[float]] = {}
    by_uid = {r["uid"]: r for r in results}
    for r in results:
        for g, gr in r["by_group"].items():
            pools.setdefault(g, []).append(gr["igr"])
    for g in pools:
        pools[g].sort()
    for uid, e in evos.items():
        r = by_uid.get(uid)
        g = e.get("group") or ""
        if r and g in r["by_group"]:
            now = r["by_group"][g]["igr"]
            if e.get("igr_after") is not None:
                e["igr_after"] = round(e["igr_after"] + now - e["igr_now"], 1)
                e["evo_value"] = e["igr_after"]
            e["igr_now"] = now
            e["rank_now"] = r["by_group"][g].get("rank")
        vals = pools.get(g)
        if e.get("igr_after") is None or not vals:
            continue
        better = len(vals) - bisect.bisect_right(vals, e["igr_after"])
        e["rank_after"], e["of"] = better + 1, len(vals)


def group_label(group: Optional[str]) -> str:
    return GROUP_LABELS_NO.get(group or "", group or "-")
