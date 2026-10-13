"""Write ratings to CSV, JSON and a sortable HTML page.

Players are compared within their own position: every row shows the
player's rank among everyone who can play that position. Clicking a row
shows why the card is rated where it is, and its evo potential.
"""
from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .model import group_label, load_config
from .explain import FEEL_KEYS, explain_keys, pool_stats
from .runs import FEATURE_LABELS
from .profile import ORDER as PROFILE_ORDER
from .schema import ATTRIBUTE_LABELS, GROUP_PLURAL_NO, POSITION_GROUPS

GROUP_ORDER = ["ST", "W", "CAM", "CM", "CDM", "FB", "CB", "GK"]
ATTR_KEYS = list(ATTRIBUTE_LABELS)
ATTR_INDEX = {k: i for i, k in enumerate(ATTR_KEYS)}

CSV_COLUMNS = [
    "name", "version", "status", "estimated", "ovr", "positions", "position_group", "pos_igr", "pos_tier", "pos_rank", "pos_of",
    "pos_top_pct", "best_group", "best_igr", "feel", "pace", "skill", "playstyles", "playstyles_estimated", "role",
    "role_name", "accelerate", "off_balance_dribbling", "evo_eligible", "evo_after", "evo_gain", "evo_rank_after",
    "evo_of", "evo_reason", "run_ai", "run_decision", "run_execution", "run_vs_ovr", "run_rank", "run_of",
    "run_top_pct", "hidden_gem", "hard_to_stop", "stop_ball", "stop_run",
    "work_rate", "body", "style", "likes", "prof_feel", "prof_pace", "prof_run", "prof_dribble", "prof_finish",
    "prof_pass", "prof_physical", "prof_defend", "chem_style", "price", "warnings", "source", "uid",
]


def _evo_fields(evo: Optional[dict]) -> dict:
    if not evo:
        return {"evo_eligible": "", "evo_after": None, "evo_gain": None, "evo_rank_after": None,
                "evo_of": None, "evo_reason": ""}
    return {
        "evo_eligible": "ja" if evo.get("eligible") else "nei",
        "evo_after": evo.get("igr_after"),
        "evo_gain": evo.get("gain"),
        "evo_rank_after": evo.get("rank_after"),
        "evo_of": evo.get("of"),
        "evo_reason": "" if evo.get("eligible") else evo.get("reason", ""),
    }


def flat_row(r: dict, evo: Optional[dict] = None) -> dict:
    pg = r.get("position_group") or r["best_group"]
    g = r["by_group"].get(pg or "", {})
    row = {
        "uid": r["uid"],
        "name": r["name"],
        "version": r.get("rarity") or "",
        "status": r.get("status") or "",
        "estimated": "ja" if r.get("estimated") else "",
        "ovr": r["ovr"],
        "positions": "/".join(r["positions"]),
        "position_group": group_label(pg),
        "pos_igr": r.get("pos_igr", g.get("igr")),
        "pos_tier": r.get("pos_tier") or g.get("tier"),
        "pos_rank": r.get("pos_rank"),
        "pos_of": r.get("pos_of"),
        "pos_top_pct": r.get("pos_top_pct"),
        "best_group": group_label(r["best_group"]),
        "best_igr": r["igr"],
        "feel": r["feel"],
        "pace": g.get("pace"),
        "skill": g.get("skill"),
        "playstyles": g.get("playstyles"),
        "playstyles_estimated": "ja" if g.get("ps_estimated") else "",
        "role": g.get("role"),
        "role_name": g.get("role_name") or "",
        "accelerate": r["accelerate"] or "?",
        "off_balance_dribbling": r["off_balance_dribbling"],
        "chem_style": r["chem_style"] or "",
        "price": r["price"],
        "warnings": "; ".join(r["warnings"]),
        "source": r.get("source") or "",
    }
    row.update(_evo_fields(evo))
    ra = r.get("run_ai") or {}
    run = g.get("run") or next((v["run"] for v in r["by_group"].values() if v.get("run")), {})
    row.update(run_ai=ra.get("score"), run_decision=ra.get("decision"), run_execution=ra.get("execution"),
               run_vs_ovr=run.get("res"), run_rank=run.get("rank"), run_of=run.get("of"),
               run_top_pct=run.get("top_pct"), hidden_gem="ja" if run.get("gem") else "",
               work_rate=f"{r.get('work_rate_att') or ''}/{r.get('work_rate_def') or ''}".strip("/"),
               body=ra.get("body", ""))
    hs = r.get("hard_to_stop") or {}
    row.update(hard_to_stop=hs.get("score"), stop_ball=hs.get("ball"), stop_run=hs.get("run"))
    prof = r.get("profile") or {}
    row.update(style=prof.get("style", ""), likes="; ".join(prof.get("likes", [])),
               **{f"prof_{k}": v for k, v in (prof.get("cats") or {}).items()})
    return row


def _sort_key(row: dict):
    labels = [group_label(g) for g in GROUP_ORDER]
    pos = labels.index(row["position_group"]) if row["position_group"] in labels else len(labels)
    return (pos, row["pos_rank"] or 10**9)


def write_outputs(results: List[dict], evos: Dict[str, dict], out_dir: str, evolab: bool = False) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = sorted((flat_row(r, evos.get(r["uid"])) for r in results), key=_sort_key)

    csv_path = out / "ratings.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    json_path = out / "ratings.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                   "players": results, "evo": evos}, f, ensure_ascii=False, separators=(",", ":"))

    html_path = out / "rapport.html"
    html_path.write_text(render_html(results, evos, evolab=evolab), encoding="utf-8")
    from .site import write_assets  # fonts, icons and om.html, so the page looks the same opened from disk
    write_assets(out)
    return {"csv": str(csv_path), "json": str(json_path), "html": str(html_path)}


# ---------------------------------------------------------------- HTML
#
# The page holds every card, so data is sent as compact arrays (the script
# turns them back into objects). The explanation of a card is computed in the
# browser from its attributes and the position averages in META, the same way
# explain.add_explanations does it for the command line.

def _r1(v):
    return round(v, 1) if isinstance(v, float) else v


class _Interner:
    """Repeated strings (PlayStyle names, warnings) are sent once."""
    def __init__(self):
        self.items: List[str] = []
        self.index: Dict[str, int] = {}

    def __call__(self, text: str) -> int:
        if text not in self.index:
            self.index[text] = len(self.items)
            self.items.append(text)
        return self.index[text]


def _group_array(gr: dict, intern: _Interner) -> list:
    ps = []
    for d in gr.get("playstyle_details", []):
        if round(d["points"], 1):
            ps += [intern(d["name"]), round(d["points"], 1)]
    return [gr["igr"], gr.get("pos_tier") or gr["tier"], gr.get("rank"), gr.get("of"), gr.get("top_pct"),
            gr.get("pace"), gr.get("skill"), gr.get("core"), gr.get("playstyles"), gr.get("role"),
            intern(gr.get("role_name") or ""), _r1(gr.get("weak_foot")), _r1(gr.get("skill_moves")),
            _r1(gr.get("gk_height")), ps, 1 if gr.get("ps_estimated") else 0, _run_array(gr.get("run"), intern),
            _r1(gr.get("off_balance")), _r1(gr.get("stand_tackle")), gr.get("run_score"), gr.get("stop_score")]


def _run_array(run: Optional[dict], intern: "_Interner"):
    if not run:
        return None
    flat = lambda items: [x for k, v, m in items for x in (intern(FEATURE_LABELS.get(k, k)), v, m)]
    return [run["rank"], run["of"], run["top_pct"], run["ovr_top_pct"], 1 if run["gem"] else 0,
            flat(run.get("up", [])), flat(run.get("down", [])), run.get("res"), run.get("res_top_pct")]


def _evo_array(evo: Optional[dict], intern: _Interner):
    if not evo:
        return None
    if not evo.get("eligible"):
        return intern(evo.get("reason", ""))
    return [evo["igr_after"], evo["igr_now"], evo["gain"], evo.get("boost"), evo.get("ovr_after"),
            evo.get("rank_now"), evo.get("rank_after"), evo.get("of"), group_label(evo.get("group")),
            evo.get("accelerate_after")]


def html_row(r: dict, evo: Optional[dict], intern: _Interner) -> list:
    fp = r.get("feel_parts") or {}
    attrs = r.get("attributes") or {}
    return [
        r["name"], r.get("rarity") or "", r.get("status") or "", 1 if r.get("estimated") else 0, r["ovr"],
        "/".join(r["positions"]), group_label(r.get("position_group") or r["best_group"]), r["feel"],
        r["accelerate"] or "?", r["off_balance_dribbling"], r["price"], r["chem_style"] or "",
        intern("; ".join(r["warnings"])), intern(r.get("source") or ""), r.get("url") or "",
        r.get("height_cm"), _r1(fp.get("height")), _r1(fp.get("accelerate")), r.get("weak_foot"), r.get("skill_moves"),
        [round(attrs.get(k) or 0) for k in ATTR_KEYS],
        _evo_array(evo, intern),
        {group_label(g): _group_array(v, intern) for g, v in r["by_group"].items()},
        _ra_array(r.get("run_ai"), intern),
        r.get("gender") or "M",
        _ps_names(r, intern),
        [((r.get("profile") or {}).get("cats") or {}).get(k) for k in PROFILE_ORDER],
        intern((r.get("profile") or {}).get("style") or ""),
        [intern(x) for x in (r.get("profile") or {}).get("likes", [])],
        [hs["score"], hs["ball"], hs["run"]] if (hs := r.get("hard_to_stop")) else 0,
    ]


def _ps_names(r: dict, intern: "_Interner") -> list:
    """Every PlayStyle on the card (name + '+' for PS+), for the PlayStyle filter.
    Empty when the card's PlayStyles are unknown."""
    if not r.get("ps_known", True):
        return []
    for v in r["by_group"].values():
        return [intern(d["name"]) for d in v.get("playstyle_details", [])]
    return []


def _ra_array(ra: Optional[dict], intern: "_Interner"):
    if not ra:
        return None
    return [ra["score"], ra.get("vs_ovr"), intern(ra["body"]), intern(ra["wr"]), ra.get("decision"), ra.get("execution")]


def _meta(results: List[dict], cfg: dict, intern: _Interner) -> dict:
    wcfg = cfg["weights"]
    pools: Dict[str, List[dict]] = {}
    for r in results:
        for g in r["by_group"]:
            pools.setdefault(g, []).append(r)
    stats, skill = {}, {}
    for g, pool in pools.items():
        skill_keys, keys = explain_keys(g, wcfg)
        st = pool_stats(pool, keys)
        stats[group_label(g)] = [[ATTR_INDEX[k], round(m, 4), round(sd, 4)] for k, (m, sd) in st.items()]
        skill[group_label(g)] = [[ATTR_INDEX[k], w] for k, w in wcfg["skill"][g].items() if not k.startswith("_")]
    ecfg = wcfg.get("evo", {})
    xcfg = wcfg.get("explain", {})
    return {
        "order": [group_label(g) for g in GROUP_ORDER],
        "labels": [ATTRIBUTE_LABELS[k] for k in ATTR_KEYS],
        "idx": ATTR_INDEX,
        "plural": {group_label(g): GROUP_PLURAL_NO[g] for g in GROUP_ORDER},
        "blend": {group_label(g): v for g, v in wcfg["blend"].items() if not g.startswith("_")},
        "evo": {k: ecfg.get(k) for k in ("max_ovr", "target_ovr", "points_per_ovr", "max_boost", "excluded_versions")},
        "x": {"sz": xcfg.get("strength_z", 0.6), "wz": xcfg.get("weakness_z", -0.6),
              "ms": xcfg.get("max_strengths", 4), "mw": xcfg.get("max_weaknesses", 3),
              "min": xcfg.get("min_pool_size", 10)},
        "stats": stats, "skill": skill, "feel": [ATTR_INDEX[k] for k in FEEL_KEYS],
        "fw": [[ATTR_INDEX[k], w] for k, w in wcfg["feel"]["attributes"].items() if not k.startswith("_")],
        "gk": group_label("GK"),
        "run": _run_meta(results, cfg),
        "prof": _prof_meta(cfg),
        "ob": {"start": wcfg.get("off_balance", {}).get("start", 75),
               "gf": {group_label(g): f for g, f in wcfg.get("off_balance", {}).get("group_factor", {}).items()}},
    }


def _prof_meta(cfg: dict) -> Optional[dict]:
    """order/labels for every category in the data rows; "panel" = the ones shown in the
    Profil panel and the style (Løps-IQ/Løpseffekt/Vanskelig å stoppe are only for filters and ranking);
    "use" = the ones this config defines (the combo chips)."""
    if "profile" not in cfg["weights"]:
        return None
    from .profile import order, style_keys
    cats = cfg["weights"]["profile"]["categories"]
    return {"order": PROFILE_ORDER, "labels": [cats.get(k, {}).get("label", k) for k in PROFILE_ORDER],
            "panel": style_keys(cfg), "use": order(cfg)}


def _run_meta(results: List[dict], cfg: dict) -> Optional[dict]:
    rc = cfg["weights"].get("run_ai")
    if not rc:
        return None
    from .runs import similarity_stats
    fw = {k: v for k, v in rc["similar"]["features"].items() if not k.startswith("_")}
    stats = similarity_stats(results, rc)
    return {
        "groups": [group_label(g) for g in rc["groups"]],
        "gem": {k: v for k, v in rc["gem"].items() if not k.startswith("_")},
        "wrv": {k: v for k, v in rc["work_rate_values"].items() if not k.startswith("_")},
        "sim": [[k, round(m, 4), round(sd, 4), fw[k]] for k, (m, sd) in stats.items()],
        "calibrated": rc.get("calibrated"),
        "dropped": list(rc.get("dropped", {}).values()),
    }


def render_html(results: List[dict], evos: Dict[str, dict], cfg: Optional[dict] = None, evolab: bool = False) -> str:
    cfg = cfg or load_config()
    intern = _Interner()
    data = [html_row(r, evos.get(r["uid"]), intern) for r in results]
    meta = _meta(results, cfg, intern)
    meta["strings"] = intern.items

    def dump(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    meta["evolab"] = bool(evolab)
    meta["pg"] = {p: g for p, g in POSITION_GROUPS.items()}
    stamp = html.escape(datetime.now().strftime("%d.%m.%Y kl. %H:%M"))
    link = '<a href="evolab.html">Evo Lab</a>' if evolab else ""
    return (_HTML.replace("__CSS__", PAGE_CSS).replace("__DATA__", dump(data)).replace("__STAMP__", stamp)
            .replace("__META__", dump(meta)).replace("__EVOLAB__", link))


_DIR = Path(__file__).resolve().parent
_HTML = (_DIR / "report_page.html").read_text(encoding="utf-8")
PAGE_CSS = (_DIR / "page_style.css").read_text(encoding="utf-8")
