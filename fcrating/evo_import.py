"""Turn text copied from an evolution page (FUTBIN, FUT.GG, EA's app) into an evo for Evo Lab.

The text is scanned for known patterns, so the layout does not matter much:

  requirements  "Overall max 81", "Max OVR 81", "Overall: Max. 74", "OVR min 81",
                "Pace max 85", "Max PS 7", "Max PS+ 0", "Total Pos. max 3",
                "Positions: ST, CAM", "Not: CB, CM" / "Excluded positions: CB"
  upgrades      "+7 Finishing 83", "+7 Finishing (max 83)", "Finishing +7 (max 83)",
                "Finishing +7 | 83", "Overall +6 (max 83)", "+40 OVR 79",
                "Skill Moves +1 (max 3)", "+2 SM3", "Weak Foot +2 (max 3)", "+2 WF3",
                "Pace +2 (max 84)" (main stats raise all their attributes)
  PlayStyles    "PlayStyle: Technical", "PlayStyle+: Finesse Shot", "Reward: Tiki Taka 3"
                (3 = PlayStyle, 4 = PlayStyle+, as FUT.GG writes them)

The result is printed so you can check it, and saved to data/mine_evoer.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

STAT_ALIASES = {
    "acceleration": ["acceleration"], "sprint_speed": ["sprint speed"],
    "positioning": ["att. position", "att. positioning", "attacking position", "att position", "positioning"],
    "finishing": ["finishing"], "shot_power": ["shot power"], "long_shots": ["long shots"], "volleys": ["volleys"],
    "penalties": ["penalties"], "vision": ["vision"], "crossing": ["crossing"],
    "fk_accuracy": ["fk accuracy", "free kick accuracy", "free kick", "fk acc."],
    "short_passing": ["short passing", "short pass"], "long_passing": ["long passing", "long pass"], "curve": ["curve"],
    "agility": ["agility"], "balance": ["balance"], "reactions": ["reactions"], "ball_control": ["ball control"],
    "dribbling": ["dribbling"], "composure": ["composure"], "interceptions": ["interceptions"],
    "heading_accuracy": ["heading accuracy", "heading acc.", "heading acc", "heading"],
    "def_awareness": ["defensive awareness", "def. awareness", "def. aware", "def awareness"],
    "standing_tackle": ["standing tackle", "stand tackle"], "sliding_tackle": ["sliding tackle", "slide tackle"],
    "jumping": ["jumping"], "stamina": ["stamina"], "strength": ["strength"], "aggression": ["aggression"],
    "gk_diving": ["gk diving", "diving"], "gk_handling": ["gk handling", "handling"], "gk_kicking": ["gk kicking", "kicking"],
    "gk_reflexes": ["gk reflexes", "reflexes"], "gk_positioning": ["gk positioning"],
}
FACE = {"pace": "pace", "shooting": "shooting", "passing": "passing", "defending": "defending", "physical": "physical",
        "physicality": "physical"}
POSITIONS = ["ST", "CF", "LW", "RW", "LM", "RM", "CAM", "CM", "CDM", "LB", "RB", "LWB", "RWB", "CB", "GK"]


def _alias_table() -> List[tuple]:
    out = [(a, k) for k, lst in STAT_ALIASES.items() for a in lst]
    out.sort(key=lambda t: len(t[0]), reverse=True)  # longest first: "gk positioning" before "positioning"
    return out


def _num(m) -> Optional[int]:
    return int(m) if m is not None and m != "" else None


def _positions(text: str) -> List[str]:
    return [p for p in re.findall(r"[A-Z]{2,3}", text.upper()) if p in POSITIONS]


def parse(text: str, name: Optional[str] = None, key: Optional[str] = None) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    flat = " ".join(lines)
    low = flat.lower()
    req: Dict[str, object] = {}

    def find(patterns):
        for pat in patterns:
            m = re.search(pat, low)
            if m:
                return int(m.group(1))
        return None

    req["max_ovr"] = find([r"(?:overall|ovr|rating)\s*:?\s*max\.?\s*(\d{2})", r"max\.?\s*(?:overall|ovr|rating)\s*:?\s*(\d{2})",
                           r"(?:overall|ovr)\s*min\.?\s*\d{2}\s*max\.?\s*(\d{2})"])
    req["min_ovr"] = find([r"(?:overall|ovr|rating)\s*:?\s*min\.?\s*(\d{2})", r"min\.?\s*(?:overall|ovr|rating)\s*:?\s*(\d{2})"])
    req["max_pace"] = find([r"pace\s*:?\s*max\.?\s*(\d{2})", r"max\.?\s*pace\s*:?\s*(\d{2})"])
    req["max_psp"] = find([r"max\.?\s*(?:ps|playstyles?)\s*\+\s*:?\s*(\d)", r"(?:ps|playstyles?)\s*\+\s*:?\s*max\.?\s*(\d)"])
    req["max_ps"] = find([r"max\.?\s*(?:ps|playstyles?)(?!\s*\+)\s*:?\s*(\d)\b", r"(?:ps|playstyles?)(?!\s*\+)\s*:?\s*max\.?\s*(\d)\b"])
    req["max_positions"] = find([r"(?:total\s*)?pos(?:itions)?\.?\s*:?\s*max\.?\s*(\d)", r"max\.?\s*pos(?:itions)?\.?\s*:?\s*(\d)"])
    pos, notpos = [], []
    for ln in lines:
        l = ln.lower()
        if re.match(r"^(not|excluded|exclude|ikke)\b", l) or "excluded position" in l or l.startswith("not "):
            notpos += _positions(ln.split(":", 1)[-1] if ":" in ln else ln[3:])
        elif re.match(r"^(positions?|posisjon(er)?)\b", l):
            pos += _positions(ln.split(":", 1)[-1] if ":" in ln else re.sub(r"^\w+", "", ln))
    req["positions"] = list(dict.fromkeys(pos))
    req["not_positions"] = list(dict.fromkeys(p for p in notpos if p not in pos))
    gk_only = req["positions"] == ["GK"]

    stats: Dict[str, list] = {}
    face: Dict[str, list] = {}
    up: Dict[str, object] = {}
    names = "|".join(re.escape(a) for a, _ in _alias_table()) + "|" + "|".join(FACE) + "|overall|ovr|skill moves|skills|sm|weak foot|wf"
    stat_re = f"(?P<s>{names})"
    pats = [
        re.compile(r"\+\s*(?P<g>\d{1,2})\s+" + stat_re + r"\s*(?:\(\s*)?(?:max\.?\s*|maks\s*|→\s*|to\s*|\|\s*)?(?P<c>\d{1,2})\b"),
        re.compile(stat_re + r"\s*:?\s*\+\s*(?P<g>\d{1,2})\s*(?:\(\s*)?(?:max\.?\s*|maks\s*|→\s*|to\s*|\|\s*)?(?P<c>\d{1,2})?\b"),
    ]
    aliases = dict(_alias_table())
    has_face = any(re.search(rf"\b{f}\s*:?\s*\+\s*\d", low) or re.search(rf"\+\s*\d+\s+{f}\b", low) for f in FACE)
    for pat in pats:
        for m in pat.finditer(low):
            s, g, c = m.group("s"), _num(m.group("g")), _num(m.group("c"))
            if g is None:
                continue
            if s in ("overall", "ovr"):
                up.setdefault("ovr", [g, c if c else 99])
            elif s in ("skill moves", "skills", "sm"):
                up.setdefault("sm", [g, c if c else 5])
            elif s in ("weak foot", "wf"):
                up.setdefault("wf", [g, c if c else 5])
            elif s in FACE or (s == "dribbling" and has_face and "ball control" not in low):
                face.setdefault(FACE.get(s, "dribbling"), [g, c if c else 99])
            else:
                k = aliases.get(s)
                if k == "positioning" and gk_only:
                    k = "gk_positioning"
                if k:
                    stats.setdefault(k, [g, c if c else 99])
    ps, psp = [], []
    try:
        from .model import load_config
        known = [n for n in load_config()["playstyles"]["playstyles"] if not str(n).startswith("_")]
    except Exception:
        known = []
    names = set()
    for n in sorted(known, key=len, reverse=True):
        # "Tiki Taka | 3" or "Tiki Taka 3": the number is EA's cap (only added while the card has fewer PlayStyles)
        for m in re.finditer(r"(?<!\w)" + re.escape(n.lower()) + r"(?!\w)(\s*\+)?(?:\s*\|?\s*([2-8])\b)?", low):
            before = low[max(0, m.start() - 14):m.start()]
            plus = bool(m.group(1)) or "playstyle+" in before or "ps+" in before
            cap = int(m.group(2)) if m.group(2) else None
            if n not in names:
                names.add(n)
                (psp if plus else ps).append([n, cap] if cap else n)
    if stats:
        up["stats"] = stats
    if face:
        up["face"] = face
    if ps:
        up["ps"] = ps
    if psp:
        up["psp"] = psp
    title = name or (lines[0] if lines else "Egen evo")
    k = key or re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "egen_evo"
    return {"key": k, "name": title, "req": {a: b for a, b in req.items() if b not in (None, [])}, "up": up}


def describe(evo: dict) -> List[str]:
    from .schema import ATTRIBUTE_LABELS
    r, u = evo["req"], evo["up"]
    out = [f"Evo: {evo['name']} (nøkkel {evo['key']})"]
    krav = []
    if "min_ovr" in r:
        krav.append(f"OVR minst {r['min_ovr']}")
    if "max_ovr" in r:
        krav.append(f"OVR maks {r['max_ovr']}")
    if "max_pace" in r:
        krav.append(f"PAC maks {r['max_pace']}")
    if "max_ps" in r:
        krav.append(f"maks {r['max_ps']} PlayStyles")
    if "max_psp" in r:
        krav.append(f"maks {r['max_psp']} PlayStyle+")
    if "max_positions" in r:
        krav.append(f"maks {r['max_positions']} posisjoner")
    for k, v in (r.get("max_face") or {}).items():
        krav.append(f"{k.upper()[:3]} maks {v}")
    for k, v in (r.get("max_stats") or {}).items():
        krav.append(f"{ATTRIBUTE_LABELS.get(k, k)} maks {v}")
    if r.get("positions"):
        krav.append("posisjon " + "/".join(r["positions"]))
    if r.get("not_positions"):
        krav.append("ikke " + "/".join(r["not_positions"]))
    out.append("  Krav: " + (", ".join(krav) or "ingen funnet"))
    ups = []
    if "ovr" in u:
        ups.append(f"OVR +{u['ovr'][0]} (maks {u['ovr'][1]})")
    for k, (g, c) in (u.get("stats") or {}).items():
        ups.append(f"{ATTRIBUTE_LABELS.get(k, k)} +{g} (maks {c})")
    for k, (g, c) in (u.get("face") or {}).items():
        ups.append(f"{k.capitalize()} +{g} (maks {c})")
    for k, word in (("sm", "Skill moves"), ("wf", "Svakfot")):
        if k in u:
            ups.append(f"{word} +{u[k][0]} (maks {u[k][1]})")
    def ps_txt(x):
        return f"{x[0]} (bare hvis kortet har færre enn {x[1]} PlayStyles)" if isinstance(x, list) else x
    ups += [f"PlayStyle {ps_txt(x)}" for x in u.get("ps", [])] + [f"PlayStyle+ {ps_txt(x)}" for x in u.get("psp", [])]
    out.append("  Oppgraderinger: " + (", ".join(ups) or "ingen funnet"))
    return out


def save(evo: dict, path: Path, until: Optional[str] = None, cost: Optional[str] = None) -> int:
    data = {"evos": []}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = {"evos": data}
    evo = dict(evo)
    if until:
        evo["until"] = until
    if cost:
        evo["cost"] = cost
    data["evos"] = [e for e in data.get("evos", []) if e.get("key") != evo["key"]] + [evo]
    data.setdefault("_info", "Dine egne evoer for Evo Lab (py -m fcrating evo-import). Overstyrer evoer med samme nøkkel i config/evolab.json.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return len(data["evos"])
