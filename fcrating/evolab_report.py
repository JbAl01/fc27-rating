"""output/evolab.html and output/evolab.csv: the Evo Lab page.

One self-contained page. Pick the OVR the evo allows, a position and how far ahead to look,
and the cards are ranked by how good they can become (by default by their place in the
position, so positions can be mixed fairly). Rank by your taste after evo (feel, Løps-AI,
dribbling ...), or by how much a card moves like a card you love after evo ("evo twin").

The IGR formula and the evo rules are also built into the page (the same maths as
evolab.FastRater / evolab.apply, checked against Python in the tests), so a card can be
taken apart in the browser: the value of every evo in the plan, the plan that is best for
Løps-AI or for feel, and a sandbox where you pick evos, pathways and your own upgrades and
watch IGR, feel, Løps-AI, AcceleRATE and the place in the position change.
"""
from __future__ import annotations

import csv
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .evolab import BLOCK_WORDS, FastRater, _clean, _favorites, horizons, state_from
from .model import group_label
from .report import ATTR_INDEX, ATTR_KEYS, _Interner
from .schema import ATTRIBUTE_LABELS, GROUP_PLURAL_NO, TOP_LEAGUES, Player, position_group

BASE_CSS = (Path(__file__).resolve().parent / "page_style.css").read_text(encoding="utf-8")
GROUPS = ["ST", "W", "CAM", "CM", "CDM", "FB", "CB", "GK"]


def _kind(r: dict) -> str:
    v = (r.get("rarity") or "").lower()
    if r.get("status") == "lekket":
        return "leak"
    if "icon" in v:
        return "icon"
    if "hero" in v:
        return "hero"
    return "special" if r.get("status") else "base"


def _r1(v):
    return None if v is None else round(float(v), 1)


def _num(v):
    """Whole numbers without ".0" (shorter page); other values unchanged."""
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


# ---------------------------------------------------------------- maths for the page

def rate_meta(cfg: dict) -> dict:
    """Everything FastRater needs, in index form for the page."""
    w, psc = cfg["weights"], cfg["playstyles"]
    G = {}
    st = w.get("stand_tackle_tiers") or {}
    for g in GROUPS:
        bl = w["blend"][g]
        sh = w["pace"]["acceleration_share"]
        G[g] = {"b": [bl["skill"], bl["feel"], bl["pace"], bl.get("run") or 0.0, bl.get("stop") or 0.0],
                "sk": [[ATTR_INDEX[k], v] for k, v in _clean(w["skill"][g]).items() if k in ATTR_INDEX],
                "sh": sh.get(g, sh["default"]), "rp": w["roles"]["group_positions"].get(g, []),
                "wf": w["weak_foot"]["group_factor"].get(g, 0.0), "sm": w["skill_moves"]["group_factor"].get(g, 0.0),
                "ob": (w.get("off_balance") or {}).get("group_factor", {}).get(g, 0.0),
                "st": st.get("group_factor", {}).get(g, 0.0) if st else 0.0}
    ps = {}
    relc = psc["category_relevance"]
    for name, e in psc["playstyles"].items():
        if str(name).startswith("_") or not isinstance(e, dict) or "category" not in e:
            continue
        rel = e.get("relevance") or relc[e["category"]]
        d = e.get("dampen")
        damp = [ATTR_INDEX[d["attribute"]], d["from"], d["to"], d["min_factor"]] if d and d["attribute"] in ATTR_INDEX else 0
        ps[name] = [e["base"], e["plus"], [ATTR_INDEX[k] for k in e.get("synergy", []) if k in ATTR_INDEX], damp,
                    {g: rel.get(g, 0.0) for g in GROUPS}]
    run = w.get("run_ai") or {}
    dk = set(run.get("decision_features", ["positioning", "reactions", "arbeidsrate"]))
    run_w = [[ATTR_INDEX.get(k, k), v, 1 if k in dk else 0] for k, v in _clean(run.get("weights") or {}).items() if v]
    ob = w.get("off_balance")
    hs = w.get("hard_to_stop")
    hsm = 0
    if hs:
        def wl(d):
            return [[ATTR_INDEX.get(k, k), v] for k, v in _clean(d).items() if v]

        def pl(d):
            return [[k, v[0], v[1]] for k, v in _clean(d or {}).items()]
        hsm = {"ball": wl(hs["ball"]), "run": wl(hs["run"]), "share": hs.get("ball_share", 0.5),
               "acc": _clean(hs.get("accelerate_run") or {}), "psBall": pl(hs.get("playstyles_ball")),
               "psRun": pl(hs.get("playstyles_run")), "capBall": hs.get("ps_cap_ball", 4.0), "capRun": hs.get("ps_cap_run", 1.5)}
    return {
        "G": G, "feelW": [[ATTR_INDEX[k], v] for k, v in _clean(w["feel"]["attributes"]).items() if k in ATTR_INDEX],
        "feelAcc": _clean(w["feel"]["accelerate"]), "paceAcc": _clean(w["pace"]["accelerate"]),
        "acc": {k: v for k, v in w["accelerate_rules"].items() if not k.startswith("_")},
        "ps": ps, "syn": _clean(psc["synergy"]), "fac": psc["diminishing"]["factors"], "psMax": psc["diminishing"]["max_total"],
        "rolePts": _clean(w["roles"]["points"]), "wfPts": _clean(w["weak_foot"]["points"]), "smPts": _clean(w["skill_moves"]["points"]),
        "ob": {"start": ob["start"], "per_point": ob["per_point"], "max": ob["max"]} if ob else 0,
        "obdW": [[ATTR_INDEX[k], v] for k, v in _clean(w["off_balance_dribbling"]["weights"]).items()],
        "stT": st.get("tiers", []) if st else [], "runW": run_w, "hs": hsm,
        "pysum": sys.version_info >= (3, 12),  # Python 3.12+ adds floats with compensation; the page does the same
    }


def rules_meta(lab: dict) -> dict:
    r = lab["rules"]
    return {"psCap": r.get("ps_cap", 8), "pspCap": r.get("ps_plus_cap", 3), "assume": r.get("assume_ps_count_unknown", 5),
            "rpp": bool(r.get("roles_plus_plus", True)), "rppCost": r.get("roles_plus_plus_cost", ""),
            "dg": list((r.get("defense") or {}).get("groups") or []),
            "atk": list((r.get("defense") or {}).get("attack_playstyles") or []),
            "defw": {g: [[k, v] for k, v in _clean(w).items()] for g, w in _clean((r.get("defense") or {}).get("weights") or {}).items()},
            "face": {k: [[ATTR_INDEX[a], v] for a, v in _clean(wts).items()] for k, wts in _clean(r["face"]).items()}}


def evos_meta(live: List[dict]):
    out, idx = [], {}

    def stats(d):
        return [[ATTR_INDEX[k], v[0], v[1]] for k, v in d.items() if k in ATTR_INDEX and v]

    def upg(u):
        """[ovr, wf, sm, stats, face, ps, psp, roles]; ps/psp as [name, cap or 0], roles as [pos, role, level]."""
        return [list(u["ovr"]) if u["ovr"] else 0, list(u["wf"]) if u["wf"] else 0, list(u["sm"]) if u["sm"] else 0,
                stats(u["stats"]), [[k, v[0], v[1]] for k, v in u["face"].items()],
                [[n, c or 0] for n, c in u["ps"]], [[n, c or 0] for n, c in u["psp"]], [list(r) for r in u["roles"]]]
    for e in live:
        r, u = e["req"], e["up"]
        idx[e["key"]] = len(out)
        out.append([
            e["key"], e["name"], e.get("cost") or "", e.get("until") or "", 1 if e.get("premium") else 0, e.get("unchecked") or "",
            e.get("repeat", 1),
            [r["min_ovr"], r["max_ovr"], r["max_pace"], r["max_ps"], r["max_psp"], r["max_positions"], r["positions"],
             r["not_positions"], r["requires_evo"] or "", r.get("born_from") or "", r.get("born_to") or ""],
            upg(u) + [[[pa["label"]] + upg(pa) for pa in u["paths"]]],
            e.get("note") or "", e.get("sources") or [],
        ])
    return out, idx


def card_consts(p: Player, g: str, cfg: dict) -> list:
    fr = FastRater(p, g, cfg)
    st = state_from(p)
    best = -1
    for pos in fr.role_pos:
        for lvl in (st.roles.get(pos) or {}).values():
            best = max(best, lvl)
    prim = (p.position or "").upper()
    cur = st.roles.get(prim) or {}
    return [g, fr.feel_h, fr.feel_b, fr.gk, fr.run_const.get("kort_kropp"), fr.run_const.get("arbeidsrate"),
            fr.obd_off[0] if fr.obd_off else None, fr.obd_off[1] if fr.obd_off else None, p.accelerate_source or "",
            p.height_cm, best, 1 if cur and all(v >= 2 for v in cur.values()) else 0, 1 if st.ps_unknown else 0, prim,
            p.gender or "M"]


def _seq(seq, idx, live_by_key):
    out = []
    for key, label in seq:
        if key not in idx:
            return None
        paths = [pa["label"] for pa in live_by_key[key]["up"]["paths"]]
        out.append([idx[key], paths.index(label) if label in paths else -1])
    return out


def targets_meta(results: List[dict], lab: dict, cfg: dict):
    """Cards you can pick as the "evo twin" target: favourites, Icons, Heroes and the best
    cards in every outfield position, with their movement profile."""
    rc = cfg["weights"].get("run_ai")
    if not rc:
        return [], {"keys": [], "st": []}
    from .runs import _sim_value, similarity_stats
    stats = similarity_stats(results, rc)
    keys = list(stats)
    fw = _clean(rc["similar"]["features"])
    favs = {r["uid"] for r in _favorites(lab, results)}
    # every outfield card can be a target (not only the run positions): the movement profile is attributes,
    # height and work rate, which all outfield cards have
    pool = [r for r in results if (r.get("position") or "").upper() != "GK" and any(g != "GK" for g in r["by_group"])
            and sum(1 for k in keys if _sim_value(r, k, rc) is not None) >= 0.8 * len(keys)]
    chosen = {}
    for r in pool:
        v = (r.get("rarity") or "").lower()
        if r["uid"] in favs or "icon" in v or "hero" in v or (r.get("ovr") or 0) >= 88:
            chosen[r["uid"]] = r
    for g in ("ST", "W", "CAM", "CM", "CDM", "FB", "CB"):
        best = sorted((r for r in pool if g in r["by_group"]), key=lambda r: r["by_group"][g]["igr"], reverse=True)[:150]
        chosen.update({r["uid"]: r for r in best})
    out = []
    for r in sorted(chosen.values(), key=lambda r: (r["uid"] not in favs, -(r.get("ovr") or 0), r["name"]))[:2000]:
        feats = [_r1(_sim_value(r, k, rc)) for k in keys]
        g = r.get("position_group") or r.get("best_group")
        out.append([r["name"], r.get("rarity") or "", group_label(g), feats, 1 if r["uid"] in favs else 0])
    return out, {"keys": keys, "st": [[round(m, 4), round(sd, 4), fw.get(k, 0.0)] for k, (m, sd) in stats.items()],
                 "sumw": sum(fw.values()),
                 "accv": _clean(rc["similar"].get("accelerate_values", {}))}


# ---------------------------------------------------------------- rows

def row(r: dict, s: dict, p: Player, raw_now: float, intern: _Interner, idx: dict, live_by_key: dict, cfg: dict) -> list:
    g = s["g"]
    lv = s["live"]
    med = s.get("med") or {}
    plans = [[_seq(lv.get("seq", []), idx, live_by_key) or [], 1 if lv.get("roles") else 0]]
    for metric in ("run", "feel", "stp", "def"):  # plans 1-4 on the page
        a = (lv.get("alt") or {}).get(metric)
        sq = _seq(a["seq"], idx, live_by_key) if a else None
        plans.append([sq, 1 if a.get("roles") else 0] if a and sq is not None else 0)
    base = [_num(p.attributes.get(k)) for k in ATTR_KEYS]
    while base and base[-1] is None:
        base.pop()
    cats = s.get("cats") or {}
    st = s.get("stops")
    nowr, liver, endr = (s.get("runs") or {}).get("now") or [None] * 3, (s.get("runs") or {}).get("live") or [None] * 3, \
        (s.get("runs") or {}).get("end") or [None] * 3
    return [
        r["name"], intern(r.get("rarity") or ""), r.get("ovr"), intern("/".join(r.get("positions") or [])), group_label(g),
        r.get("gender") or "M", _kind(r), s["now"], s["rank_now"],
        [[h["p10"], h["p50"], h["p90"], h["op"], h["ovr"], h["rank"]] + ([h["z"]] if h.get("z") else []) for h in s["h"]],
        -1 if s["when"] is None else s["when"], s["gain"], 1 if s["coarse"] else 0,
        intern(s["like"][0] + "|" + s["like"][1]) if s.get("like") else -1,
        s.get("access"), [[intern(BLOCK_WORDS.get(k, k)), pc] for k, pc in s.get("block", [])],
        [s["dna"]["pts"], s["dna"]["top"], s["dna"].get("acc_cap") or "", [[intern(c[0]), c[1]] for c in s["dna"]["chips"]]],
        [[f[0], f[1]] for f in s.get("fav", [])],
        [[intern(t) for t in lv.get("tips", [])], [[intern(a), intern(b)] for a, b in lv.get("skip", [])],
         [[intern(a), intern(b)] for a, b in lv.get("near", [])], [[intern(a), intern(b)] for a, b in lv.get("chk", [])]],
        plans,
        [[x for k, b0, a in med.get("d", []) if k in ATTR_INDEX for x in (ATTR_INDEX[k], _num(a))], [intern(x) for x in med.get("ps", [])],
         [intern(x) for x in med.get("psp", [])], med.get("wf"), med.get("sm"), (med.get("ovr") or [None, None])[1],
         med.get("acc") or "", _r1(med.get("feel")), _r1(med.get("pace"))],
        [r.get("accelerate") or "", _r1(r.get("feel")), _r1((r["by_group"].get(g) or {}).get("pace"))],
        [nowr, liver, endr],
        [cats.get("now"), cats.get("live"), cats.get("end")] if cats.get("now") is not None else 0,
        1 if s.get("ps_est") else 0,
        base,
        card_consts(p, g, cfg),
        [intern(x) for x in p.playstyles], [intern(x) for x in p.playstyles_plus], p.weak_foot, p.skill_moves,
        round(s["now"] - raw_now, 2),
        1 if s.get("runcard") else 0,
        [_r1(lv.get("feel")), lv.get("acc") or "", _r1(lv.get("pace"))],
        [st.get("now"), st.get("live"), st.get("end")] if st else 0,
        intern(r.get("league") or ""),
        intern(r.get("nation") or ""),
        p.birthdate or "",
        r.get("futgg") or "",
        intern(r.get("club") or ""),
        r.get("image") or "",
        r.get("card_image") or "",
        r.get("club_image") or "",
        r.get("nation_image") or "",
        r.get("league_image") or "",
        r.get("foot") or "",
    ]


def page_cards(summary: Dict[str, dict]) -> List[str]:
    return list(summary)


def render(summary: Dict[str, dict], results: List[dict], lab_run: dict, cfg: dict,
           players: Optional[List[Player]] = None) -> str:
    by_uid = {r["uid"]: r for r in results}
    players_by = {p.uid: p for p in (players or [])}
    intern = _Interner()
    lab = lab_run["lab"]
    live = lab_run["live"]
    evos, idx = evos_meta(live)
    live_by_key = {e["key"]: e for e in live}
    rows, thr, of, groups_seen = [], {}, {}, set()
    for uid in page_cards(summary):
        r, s, p = by_uid.get(uid), summary[uid], players_by.get(uid)
        e = lab_run["entries"].get(uid)
        if not (r and p and e):
            continue
        rows.append(row(r, s, p, e["now"], intern, idx, live_by_key, cfg))
        gl = group_label(s["g"])
        groups_seen.add(s["g"])
        thr.setdefault(gl, [h["thr"] for h in s["h"]])
        of.setdefault(gl, s["h"][0]["of"])
    lo = min([x[7] for x in rows] + [99]) if rows else 60
    hi = max([h[2] for x in rows for h in x[9]] + [lo + 10]) if rows else 100
    pools, rpool, fpool, spool = {}, {}, {}, {}
    for g in groups_seen:
        gl = group_label(g)
        pools[gl] = sorted(rr["by_group"][g]["igr"] for rr in results if g in rr["by_group"])
        rpool[gl] = sorted((rr.get("run_ai") or {}).get("score") for rr in results
                           if g in rr["by_group"] and (rr.get("run_ai") or {}).get("score") is not None)
        fpool[gl] = sorted(rr["feel"] for rr in results if g in rr["by_group"] and rr.get("feel") is not None)
        spool[gl] = sorted((rr.get("hard_to_stop") or {}).get("score") for rr in results
                           if g in rr["by_group"] and (rr.get("hard_to_stop") or {}).get("score") is not None)
    tg, sim = targets_meta(results, lab, cfg)
    catq = {}
    if cfg["weights"].get("profile"):
        from .profile import category_pools, order as _order
        cp = category_pools(results)
        for g in groups_seen:
            qs = []
            for k in _order(cfg):
                vals = sorted(cp.get(g, {}).get(k, []), reverse=True)
                qs.append([vals[min(len(vals) - 1, int(pc / 100 * (len(vals) - 1)))] for pc in range(101)] if len(vals) >= 30 else None)
            catq[group_label(g)] = qs
    prof = cfg["weights"].get("profile", {})
    from .profile import order as prof_order, style_keys
    cat_keys = prof_order(cfg) if prof else []
    favs = [c.get("name") for c in (lab.get("favorites") or {}).get("cards", [])]
    meta = {
        "psi": ps_icons(),
        "strings": intern.items, "attrs": [ATTRIBUTE_LABELS[k] for k in ATTR_KEYS], "akeys": ATTR_KEYS, "hz": horizons(lab),
        "plural": {group_label(g): pl for g, pl in GROUP_PLURAL_NO.items()},
        "groups": [group_label(g) for g in GROUPS if g in groups_seen], "gkey": {group_label(g): g for g in GROUPS},
        "lo": max(40, int(lo) - 2), "hi": min(110, int(hi) + 2), "u": lab_run["universes"], "thr": thr, "of": of,
        "total": len(summary), "expired": lab_run.get("expired", []), "usedfile": lab_run.get("used", []),
        "top": lab.get("op", {}).get("top_pct", 5), "favs": favs if any(x[17] for x in rows) else [],
        "research": lab.get("_research", ""), "checked": lab.get("_checked", ""),
        "stamp": datetime.now().strftime("%d.%m.%Y kl. %H:%M"), "rate": rate_meta(cfg), "rules": rules_meta(lab), "evos": evos,
        "toplg": TOP_LEAGUES, "pools": pools, "rpool": rpool, "fpool": fpool, "spool": spool, "targets": tg, "sim": sim, "catq": catq,
        "cats": [{"k": k, "l": prof["categories"][k]["label"], "panel": k in style_keys(cfg),
                  "src": prof["categories"][k].get("source") or "w",
                  "w": [[ATTR_INDEX[a], v] for a, v in _clean(prof["categories"][k].get("weights") or {}).items() if a in ATTR_INDEX and v],
                  "wall": sum(v for v in _clean(prof["categories"][k].get("weights") or {}).values() if v)} for k in cat_keys],
        "chem": {name: [[ATTR_INDEX[k], int(v)] for k, v in (e.get("boosts") or {}).items() if k in ATTR_INDEX]
                 for name, e in cfg["chem"]["styles"].items() if e and e.get("boosts") and e.get("verified")},
    }

    def dump(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    stamp = html.escape(datetime.now().strftime("%d.%m.%Y %H:%M"))
    return (_HTML.replace("__CSS__", BASE_CSS).replace("__DATA__", dump(rows)).replace("__META__", dump(meta))
            .replace("__STAMP__", stamp).replace("__U__", str(lab_run["universes"])).replace("__TOP__", str(meta["top"])))


CSV_COLUMNS = ["name", "version", "ovr", "position", "igr_now", "live_igr", "live_ovr", "live_plan",
               "s2_p50", "s4_p50", "year_p10", "year_p50", "year_p90", "year_ovr", "op_chance_year", "op_when",
               "gain", "run_now", "run_year", "feel_now", "feel_year", "stop_now", "stop_year", "dna_points", "dna_top_pct", "evo_access", "blocked_by",
               "favourite_likeness", "rough_estimate", "uid"]


def write(summary: Dict[str, dict], results: List[dict], lab_run: dict, cfg: dict, out_dir: str,
          players: Optional[List[Player]] = None) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    page = out / "evolab.html"
    page.write_text(render(summary, results, lab_run, cfg, players), encoding="utf-8")
    hz = horizons(lab_run["lab"])
    by_uid = {r["uid"]: r for r in results}
    rows = []
    for uid, s in summary.items():
        r = by_uid.get(uid)
        if not r:
            continue
        h = s["h"]
        runs = s.get("runs") or {}
        rows.append({
            "name": r["name"], "version": r.get("rarity") or "", "ovr": r.get("ovr"), "position": group_label(s["g"]),
            "igr_now": s["now"], "live_igr": h[0]["p50"], "live_ovr": h[0]["ovr"],
            "live_plan": " > ".join(st["name"] + (f" ({st['path']})" if st.get("path") else "") for st in s["live"]["steps"]),
            "s2_p50": h[1]["p50"] if len(h) > 1 else None, "s4_p50": h[2]["p50"] if len(h) > 2 else None,
            "year_p10": h[-1]["p10"], "year_p50": h[-1]["p50"], "year_p90": h[-1]["p90"], "year_ovr": h[-1]["ovr"],
            "op_chance_year": h[-1]["op"], "op_when": hz[s["when"]]["name"] if s["when"] is not None else "",
            "gain": s["gain"], "run_now": (runs.get("now") or [None])[0] if s.get("runcard") else None,
            "run_year": (runs.get("end") or [None])[0] if s.get("runcard") else None,
            "feel_now": r.get("feel"), "feel_year": (s.get("med") or {}).get("feel"),
            "stop_now": (r.get("hard_to_stop") or {}).get("score"), "stop_year": (s.get("med") or {}).get("stp"),
            "dna_points": s["dna"]["pts"], "dna_top_pct": s["dna"]["top"], "evo_access": s.get("access"),
            "blocked_by": ", ".join(f"{BLOCK_WORDS.get(k, k)} {pc} %" for k, pc in s.get("block", [])),
            "favourite_likeness": ", ".join(f"{n} {pc} %" for n, pc in s.get("fav", [])),
            "rough_estimate": "ja" if s["coarse"] else "", "uid": uid,
        })
    rows.sort(key=lambda x: (x["position"], -(x["year_p50"] or 0)))
    csv_path = out / "evolab.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    return {"html": str(page), "csv": str(csv_path)}


_HTML = (Path(__file__).resolve().parent / "evolab_page.html").read_text(encoding="utf-8")


def ps_icons() -> dict:
    """PlayStyle icons learned from FUT.GG pages (data/cache/futgg/ikoner.json), for the pages."""
    from pathlib import Path
    from .sources import futgg
    return futgg.load_icons(str(Path(__file__).resolve().parent.parent / "data" / "cache" / "futgg"))
