"""Evo Lab: how good can a card become through evolutions?

For every card that can be evolved, three things are computed:

1. Live chain. The evolutions that are out now (config/evolab.json "live" plus your
   own in data/mine_evoer.json) are tried in every order the requirements allow,
   with every pathway choice, and the best result for the card's position is kept.
   The plan says which order to take them in, which evos the card misses and why,
   and where the order matters ("take A before B, or the pace gets too high for A").

2. Future evos. Nobody knows the evos EA releases later, so the rest of the year is
   simulated in several parallel "futures" (universes). Each future draws evos per
   position from the ranges in config/evolab.json, the card takes every evo it
   qualifies for (most restrictive first), and the IGR is recorded after each
   horizon. The spread over the futures gives P10 / P50 / P90 and the chance that
   the card ends among the best in its position (OP chance).

3. What evolutions cannot change. Height, body type, the AcceleRATE the card can
   reach, 5-star skill moves / weak foot and existing PlayStyle+ are locked, so a
   card with a strong locked core and weak fixable stats is the best evo fodder
   ("Låst DNA"). Fast cards are shut out of many evos by "max Pace" requirements,
   which is measured as evo access.

Simulations are cached in data/evolab_cache.pkl, so a new run only simulates new
or changed cards.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import pickle
import random
import statistics
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import accelerate as acc_mod
from .model import ALL_GROUPS, CONFIG_DIR, _clean, rate
from .schema import ATTRIBUTE_LABELS, Player, parse_birthdate, position_group

ROOT = Path(__file__).resolve().parent.parent
CACHE_VERSION = 17
SEARCH_MAX_NODES = 2000   # per card; when reached, the best plan found so far is used (never worse than the quick search)
QUICK_NODES = 1500        # the fast search's budget when a run is short of time (the full search is done next run)
REASON_WORDS = {"ovr": "blir OVR-en for høy", "pace": "blir farten for høy", "ps": "får kortet for mange PlayStyles",
                "psp": "får kortet for mange PlayStyle+", "pos": "stenger posisjonene"}
BLOCK_WORDS = {"pace": "farten", "ps": "antall PlayStyles", "pos": "posisjonene", "psp": "antall PlayStyle+"}


# ---------------------------------------------------------------- config

def load_lab_config(config_dir: Optional[Path] = None) -> dict:
    d = Path(config_dir) if config_dir else CONFIG_DIR
    with open(d / "evolab.json", encoding="utf-8") as f:
        return json.load(f)


def horizons(lab: dict) -> List[dict]:
    """[{"key": "live", "name": "Nå"}, {"key": "s2", ...}, ...]"""
    return [{"key": "live", "name": "Nå", "when": "evoene som er ute nå"}] + [
        {"key": w["key"], "name": w["name"], "when": w.get("when", "")} for w in lab["future"]["waves"]]


def _pair(v) -> Optional[Tuple[int, int]]:
    if v is None:
        return None
    return int(v[0]), int(v[1])


def _ps_list(items) -> List[Tuple[str, Optional[int]]]:
    """PlayStyles an upgrade adds: "Name" or ["Name", cap]. The cap is the number EA shows next to
    the PlayStyle: it is only added while the card has fewer PlayStyles than that."""
    out = []
    for x in items or []:
        if isinstance(x, (list, tuple)):
            out.append((str(x[0]), int(x[1]) if len(x) > 1 and x[1] is not None else None))
        else:
            out.append((str(x), None))
    return out


def _roles_list(roles) -> List[Tuple[str, str, int]]:
    """{"CDM": ["Role", 1]} (old form) or [["CDM", "Role", 1], ...]."""
    if isinstance(roles, dict):
        return [(str(k).upper(), v[0], int(v[1])) for k, v in roles.items()]
    return [(str(r[0]).upper(), r[1], int(r[2])) for r in roles or []]


def _upgrade(u: dict) -> dict:
    return {"ovr": _pair(u.get("ovr")), "wf": _pair(u.get("wf")), "sm": _pair(u.get("sm")),
            "stats": {k: _pair(v) for k, v in (u.get("stats") or {}).items()},
            "face": {k: _pair(v) for k, v in (u.get("face") or {}).items()},
            "ps": _ps_list(u.get("ps")), "psp": _ps_list(u.get("psp")), "roles": _roles_list(u.get("roles"))}


def until_utc(v) -> Optional[datetime]:
    """When the evo closes, in UTC. "2026-10-22T07:00Z", or a plain date meaning 17:00 UTC
    that day (18:00 in the UK, when EA swaps content)."""
    if not v:
        return None
    t = str(v).strip()
    if len(t) == 10:
        return datetime.fromisoformat(t + "T17:00:00+00:00")
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_evo(d: dict) -> dict:
    """Normalize one evo definition (live, user file or generated)."""
    req, up = d.get("req") or {}, d.get("up") or {}
    paths = []
    for p in up.get("paths") or []:
        paths.append(dict(_upgrade(p), label=p.get("label", "")))
    return {
        "key": d["key"], "name": d.get("name", d["key"]), "cost": d.get("cost", ""), "until": d.get("until"),
        "premium": bool(d.get("premium")), "unchecked": d.get("unchecked"), "repeat": int(d.get("repeat", 1) or 1),
        "per_card": max(1, int(d.get("per_card", 1) or 1)),
        "source": d.get("source", "live"), "note": d.get("unchecked_note") or d.get("note") or "",
        "sources": list(d.get("sources") or []),
        "req": {
            "min_ovr": req.get("min_ovr"), "max_ovr": req.get("max_ovr"), "max_pace": req.get("max_pace"),
            "max_ps": req.get("max_ps"), "max_psp": req.get("max_psp"), "max_positions": req.get("max_positions"),
            "positions": [str(x).upper() for x in req.get("positions") or []],
            "not_positions": [str(x).upper() for x in req.get("not_positions") or []],
            "requires_evo": req.get("requires_evo"),
            "born_from": parse_birthdate(req.get("born_from")), "born_to": parse_birthdate(req.get("born_to")),
        },
        "up": dict(_upgrade(up), paths=paths, rarity_after=up.get("rarity_after")),
    }


def user_evos_path() -> Path:
    return ROOT / "data" / "mine_evoer.json"


def auto_evos_path() -> Path:
    """Evos added by the daily check (data/auto_evoer.json). Your own file overrides it."""
    return ROOT / "data" / "auto_evoer.json"


def used_evos_path() -> Path:
    return ROOT / "data" / "brukte_evoer.json"


def load_used(path: Optional[Path] = None) -> List[str]:
    """Evos you have used up on other cards (keys or names, lower case), from data/brukte_evoer.json."""
    p = Path(path) if path else used_evos_path()
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("brukt", []) if isinstance(data, dict) else data
    return [str(x).strip().lower() for x in items if str(x).strip()]


def save_used(items: List[str], path: Optional[Path] = None) -> Path:
    p = Path(path) if path else used_evos_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"_info": "Evoer du har brukt opp på andre kort. Evo Lab og rapporten regner uten dem. "
                            "Endre med: py -m fcrating brukt", "brukt": sorted(set(items))}, f, ensure_ascii=False, indent=2)
    return p


def _read_evos(p: Path, source: str) -> List[dict]:
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("evos", data) if isinstance(data, dict) else data
    return [dict(e, source=source) for e in items]


def load_user_evos(path: Optional[Path] = None) -> List[dict]:
    """Evos from your own file (data/mine_evoer.json) and the daily check (data/auto_evoer.json).
    With a path, only that file is read. The same key in your own file wins over the daily check."""
    if path:
        return _read_evos(Path(path), "egen")
    own = _read_evos(user_evos_path(), "egen")
    keys = {e["key"] for e in own}
    return own + [e for e in _read_evos(auto_evos_path(), "auto") if e["key"] not in keys]


def check_evo(d: dict, min_sources: int = 0, playstyles: Optional[set] = None) -> List[str]:
    """Problems with one evo definition (an empty list means it is fine). Used by evo-sjekk, so a
    wrong entry in data/auto_evoer.json is caught before it reaches the page."""
    from .evo_import import POSITIONS
    out: List[str] = []
    key = d.get("key")
    if not isinstance(key, str) or not key.strip():
        return ["mangler key"]
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        out.append("mangler name")
    try:
        end = until_utc(d.get("until"))
        if end is None and not (d.get("until_ukjent") is True and str(d.get("note", "")).strip()):
            out.append("mangler until (siste tidspunkt evoen kan startes, f.eks. 2026-10-26T17:00Z). "
                       "Er fristen ukjent i alle kilder: sett \"until_ukjent\": true og forklar i note")
    except (ValueError, TypeError):
        out.append(f"until kan ikke leses: {d.get('until')!r}")
    if not str(d.get("cost", "")).strip():
        out.append("mangler cost")
    urls = [u for u in d.get("sources") or [] if isinstance(u, str) and u.startswith("http")]
    if len(set(urls)) < min_sources:
        out.append(f"trenger minst {min_sources} ulike kilde-lenker i sources, har {len(set(urls))}")
    for k in ("repeat", "per_card"):
        v = d.get(k)
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 20):
            out.append(f"{k} må være et helt tall 1-20, er {v!r}")
    req, up = d.get("req") or {}, d.get("up") or {}
    if not req and not up:
        out.append("har verken req eller up")
    for k in ("min_ovr", "max_ovr", "max_pace", "max_ps", "max_psp", "max_positions"):
        v = req.get(k)
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 99):
            out.append(f"req.{k} må være et helt tall 0-99, er {v!r}")
    for k in ("positions", "not_positions"):
        for p in req.get(k) or []:
            if str(p).upper() not in POSITIONS:
                out.append(f"req.{k}: ukjent posisjon {p!r}")
    if req.get("min_ovr") is not None and req.get("max_ovr") is not None and req["min_ovr"] > req["max_ovr"]:
        out.append("req.min_ovr er større enn req.max_ovr")
    for k in ("born_from", "born_to"):
        if req.get(k) is not None and (not isinstance(req[k], str) or parse_birthdate(req[k]) != req[k]):
            out.append(f"req.{k} må være en dato som 2003-10-09, er {req[k]!r}")

    def pair(label, v, hi):
        if v is None:
            return
        if (not isinstance(v, (list, tuple)) or len(v) != 2 or not all(isinstance(x, int) and not isinstance(x, bool) for x in v)
                or v[0] < 0 or not 0 <= v[1] <= hi):
            out.append(f"{label} må være [økning, maks], er {v!r}")

    def block(prefix, u):
        pair(f"{prefix}ovr", u.get("ovr"), 99)
        pair(f"{prefix}wf", u.get("wf"), 5)
        pair(f"{prefix}sm", u.get("sm"), 5)
        for a, v in (u.get("stats") or {}).items():
            if a not in ATTRIBUTE_LABELS:
                out.append(f"{prefix}stats: ukjent attributt {a!r}")
            pair(f"{prefix}stats.{a}", v, 99)
        for f_, v in (u.get("face") or {}).items():
            if f_ not in ("pace", "shooting", "passing", "defending", "physical", "dribbling"):
                out.append(f"{prefix}face: ukjent hovedtall {f_!r}")
            pair(f"{prefix}face.{f_}", v, 99)
        for kind in ("ps", "psp"):
            for name, cap in _ps_list(u.get(kind)):
                if playstyles is not None and name not in playstyles:
                    out.append(f"{prefix}{kind}: ukjent PlayStyle {name!r}")
                if cap is not None and not 1 <= cap <= 12:
                    out.append(f"{prefix}{kind}: tak {cap} for {name} ser feil ut")
        try:
            for pos, role, lv in _roles_list(u.get("roles")):
                if pos not in POSITIONS or lv not in (1, 2):
                    out.append(f"{prefix}roles: {pos}/{role}/{lv} ser feil ut")
        except (TypeError, ValueError, IndexError):
            out.append(f"{prefix}roles kan ikke leses")

    try:
        block("up.", up)
        for i, p in enumerate(up.get("paths") or []):
            if not str(p.get("label", "")).strip():
                out.append(f"up.paths[{i}] mangler label")
            block(f"up.paths[{i}].", p)
        parse_evo(d)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        out.append(f"kan ikke leses: {exc}")
    return out


def active_live(lab: dict, today: Optional[date] = None, user_file: Optional[Path] = None,
                now: Optional[datetime] = None) -> Tuple[List[dict], List[str]]:
    """Live evos you can still start (config + your own file). Returns (evos, expired names).
    'today' (a date) means noon UTC that day; without it the current time is used."""
    if now is None:
        now = datetime(today.year, today.month, today.day, 12, tzinfo=timezone.utc) if today else datetime.now(timezone.utc)
    rules = lab["rules"]
    out, expired, seen = [], [], set()
    own = load_user_evos(user_file)
    own_keys = {e["key"] for e in own}
    for raw in own + [e for e in lab.get("live", []) if e["key"] not in own_keys]:
        e = parse_evo(raw)
        if e["key"] in seen:
            continue
        seen.add(e["key"])
        end = until_utc(e["until"])
        if end and end <= now:
            expired.append(e["name"])
            continue
        if e["premium"] and not rules.get("include_premium", True):
            continue
        out.append(e)
    return out, expired


# ---------------------------------------------------------------- card state

class State:
    __slots__ = ("attrs", "ovr", "ps", "psp", "wf", "sm", "roles", "positions", "done", "rarity", "ps_unknown", "born", "pos_unsure")

    def copy(self) -> "State":
        s = State.__new__(State)
        s.attrs, s.ovr = dict(self.attrs), self.ovr
        s.ps, s.psp = list(self.ps), list(self.psp)
        s.wf, s.sm = self.wf, self.sm
        s.roles = {k: dict(v) for k, v in self.roles.items()}
        s.positions, s.done, s.rarity, s.ps_unknown = self.positions, list(self.done), self.rarity, self.ps_unknown
        s.born, s.pos_unsure = self.born, self.pos_unsure
        return s

    def key(self) -> tuple:
        # attrs keep their key order through copies (evos never add keys), so values() is enough
        return (tuple(self.attrs.values()), self.ovr, tuple(sorted(self.ps)), tuple(sorted(self.psp)), self.wf, self.sm,
                tuple(sorted((p, tuple(sorted(r.items()))) for p, r in self.roles.items())))


def positions_unsure(p: Player) -> bool:
    """EA's ratings page lists at most three alternative positions, so a card with three may play more (a CDM
    the list lacks, say). Until FUT.GG has confirmed the full list, the evos that depend on positions are «sjekk selv»."""
    return len(p.alt_positions or []) >= 3 and not p.positions_complete


def pos_unsure_text(r: dict) -> str:
    what = (f"må kunne spille {'/'.join(r['positions'])}" if r["positions"]
            else f"kortet kan ikke spille {', '.join(r['not_positions'])}" if r["not_positions"] else f"maks {r['max_positions']} posisjoner")
    return f"{what}. Venter på den fulle posisjonslisten fra FUT.GG (EA oppgir bare tre alternative), den hentes automatisk"


def state_from(p: Player) -> State:
    s = State.__new__(State)
    s.attrs = {k: float(v) for k, v in p.attributes.items() if v is not None}
    s.ovr = int(p.ovr or 0)
    s.ps, s.psp = list(p.playstyles), list(p.playstyles_plus)
    s.wf, s.sm = p.weak_foot, p.skill_moves
    s.roles = {k: dict(v) for k, v in (p.roles or {}).items()}
    s.positions = tuple(x.upper() for x in [p.position] + list(p.alt_positions))
    s.done, s.rarity = [], p.rarity or ""
    s.ps_unknown = not (p.playstyles or p.playstyles_plus or p.playstyles_complete)
    s.born = p.birthdate or None
    s.pos_unsure = positions_unsure(p)
    return s


def round_half_up(x: float) -> int:
    """EA rounds the main stats with .5 up (Python's round() takes .5 to the even number)."""
    return int(math.floor(x + 0.5 + 1e-9))


def face_value(attrs: Dict[str, float], which: str, rules: dict) -> Optional[float]:
    w = _clean(rules["face"][which])
    if not all(k in attrs for k in w):
        return None
    return round_half_up(sum(attrs[k] * v for k, v in w.items()))


def ps_count(st: State, rules: dict) -> int:
    n = len(st.ps) + len(st.psp)
    return max(n, int(rules.get("assume_ps_count_unknown", 5))) if st.ps_unknown and n == 0 else n


def norsk_dato(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}. {MONTHS[int(m) - 1]} {y}"


MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober",
          "november", "desember"]


def birth_text(r: dict) -> str:
    """The age requirement in Norwegian, e.g. 'født 9. oktober 2003 eller senere'."""
    a, b = r.get("born_from"), r.get("born_to")
    if a and b:
        return f"født mellom {norsk_dato(a)} og {norsk_dato(b)}"
    if a:
        return f"født {norsk_dato(a)} eller senere"
    if b:
        return f"født {norsk_dato(b)} eller tidligere"
    return ""


def birth_block(r: dict, born: Optional[str]) -> Optional[Tuple[str, str]]:
    """('age', reason) when the card is outside the evo's age requirement. ('age?', ...) when the
    date of birth is unknown (the evo is then shown as «sjekk selv»). None when it fits."""
    if not (r.get("born_from") or r.get("born_to")):
        return None
    if not born:
        return "age?", f"spilleren må være {birth_text(r)} (fødselsdato mangler)"
    if (r.get("born_from") and born < r["born_from"]) or (r.get("born_to") and born > r["born_to"]):
        return "age", f"født {norsk_dato(born)}, evoen krever {birth_text(r)}"
    return None


def check(evo: dict, st: State, rules: dict) -> Optional[Tuple[str, str]]:
    """None if the card can enter the evo now, else (category, Norwegian reason)."""
    r = evo["req"]
    if r["positions"] and not any(p in r["positions"] for p in st.positions):
        return ("pos?", pos_unsure_text(r)) if st.pos_unsure else ("pos", "feil posisjon")
    bad = [p for p in st.positions if p in r["not_positions"]]
    if bad:
        return "pos", f"har posisjonen {bad[0]}"
    if r["max_positions"] is not None and len(st.positions) > r["max_positions"]:
        return "pos", f"{len(st.positions)} posisjoner (maks {r['max_positions']})"
    if st.pos_unsure and (r["not_positions"] or r["max_positions"] is not None):
        return "pos?", pos_unsure_text(r)
    age = birth_block(r, st.born)
    if age:
        return age
    if r["requires_evo"] and r["requires_evo"] not in st.done:
        return "pre", "krever forrige evo i kjeden"
    per = evo.get("per_card", 1)
    if evo["key"] in st.done and st.done.count(evo["key"]) >= per:
        # «repeatable» = several players can take it; the same card only as many times as per_card (default once)
        return "done", "allerede tatt" if per == 1 else f"allerede tatt {per} ganger"
    if r["min_ovr"] is not None and st.ovr < r["min_ovr"]:
        return "ovr", f"OVR {st.ovr} (minst {r['min_ovr']})"
    if r["max_ovr"] is not None and st.ovr > r["max_ovr"]:
        return "ovr", f"OVR {st.ovr} (maks {r['max_ovr']})"
    if r["max_pace"] is not None:
        pac = face_value(st.attrs, "pace", rules)
        if pac is not None and pac > r["max_pace"]:
            return "pace", f"PAC {pac} (maks {r['max_pace']})"
    if r["max_ps"] is not None:
        n = ps_count(st, rules)
        if n > r["max_ps"]:
            return "ps", f"{n} PlayStyles (maks {r['max_ps']})"
    if r["max_psp"] is not None and len(st.psp) > r["max_psp"]:
        return "psp", f"{len(st.psp)} PlayStyle+ (maks {r['max_psp']})"
    return None


def _raise(cur: float, gain: int, cap: int) -> float:
    return max(cur, min(cur + gain, cap))


def apply(evo: dict, st: State, rules: dict, path: Optional[dict] = None) -> State:
    """The card after the evo (and the chosen pathway)."""
    s = st.copy()
    _apply_core(evo, s, rules, path)
    return s


def _apply_core(evo: dict, s: State, rules: dict, path: Optional[dict]) -> None:
    """Apply the evo to s in place: the levels everyone gets first, then the chosen option, in the
    same order as the game (so an attribute in both is raised twice, each time up to its own max)."""
    up = evo["up"]
    parts = [up] + ([path] if path else [])
    a = s.attrs
    for u in parts:
        for k, (gain, cap) in u["stats"].items():
            if k in a and a[k] < cap:
                a[k] = min(a[k] + gain, cap)
    for u in parts:
        for which, (gain, cap) in u["face"].items():
            now = face_value(a, which, rules)
            if now is None or now >= cap:
                continue
            add = min(gain, cap - now)
            for k in _clean(rules["face"][which]):
                a[k] = min(99.0, a[k] + add)
    for u in parts:
        if u["ovr"] and s.ovr < u["ovr"][1]:
            s.ovr = int(min(s.ovr + u["ovr"][0], u["ovr"][1]))
        if u["wf"] and s.wf is not None and s.wf < u["wf"][1]:
            s.wf = int(min(s.wf + u["wf"][0], u["wf"][1]))
        if u["sm"] and s.sm is not None and s.sm < u["sm"][1]:
            s.sm = int(min(s.sm + u["sm"][0], u["sm"][1]))
    ps_cap, psp_cap = rules.get("ps_cap", 8), rules.get("ps_plus_cap", 3)
    for u in parts:
        for name, cap in u["ps"]:
            n = len(s.ps) + len(s.psp)
            if name not in s.ps and name not in s.psp and n < ps_cap and (cap is None or n < cap):
                s.ps.append(name)
    for u in parts:
        for name, cap in u["psp"]:
            if name in s.psp or len(s.psp) >= psp_cap or (cap is not None and len(s.psp) >= cap):
                continue
            if name in s.ps:
                s.ps.remove(name)
            s.psp.append(name)
    for u in parts:
        for pos, role, level in u["roles"]:
            cur = s.roles.setdefault(pos, {})
            cur[role] = max(cur.get(role, 0), level)
    if up["rarity_after"]:
        s.rarity = up["rarity_after"]
    s.done.append(evo["key"])


def roles_plus_plus(st: State, primary: str) -> Tuple[State, bool]:
    """The Roles++ evo for the primary position (all roles there to ++)."""
    cur = st.roles.get(primary) or {}
    if cur and all(v >= 2 for v in cur.values()):
        return st, False
    s = st.copy()
    s.roles[primary] = {k: 2 for k in cur} if cur else {"Roles++": 2}
    return s, True


def _obd_weights(cfg: dict) -> Dict[str, float]:
    return _clean(cfg["weights"]["off_balance_dribbling"]["weights"])


def to_player(p: Player, st: State, rules: dict, cfg: Optional[dict] = None) -> Player:
    obd = p.off_balance_dribbling
    if obd is not None:
        w = _obd_weights(cfg) if cfg else {"agility": 0.4, "balance": 0.3, "dribbling": 0.3}
        before = acc_mod.off_balance_dribbling(p.attributes, w)
        after = acc_mod.off_balance_dribbling(st.attrs, w)
        if before is not None and after is not None:
            obd = round(obd + after - before, 1)
    return replace(p, attributes=dict(st.attrs), ovr=st.ovr, playstyles=list(st.ps), playstyles_plus=list(st.psp),
                   weak_foot=st.wf, skill_moves=st.sm, roles={k: dict(v) for k, v in st.roles.items()},
                   playstyles_complete=p.playstyles_complete or bool(st.ps or st.psp) and not st.ps_unknown,
                   off_balance_dribbling=obd, rarity=st.rarity or p.rarity)


ACC_ANY = "*"   # the plan search's upper bound: the best AcceleRATE add-on of each kind, whatever the type


def _acc_off(table: dict, acc_type) -> float:
    if acc_type == ACC_ANY:
        return max([float(v) for k, v in table.items() if not str(k).startswith("_")] + [0.0])
    if isinstance(acc_type, tuple):   # the types the card can still get: the best add-on of them
        return max(float(table.get(x or "", 0.0)) for x in acc_type)
    return table.get(acc_type or "", 0.0)


def acc_types_possible(lo: Dict[str, float], hi: Dict[str, float], p: Player, rules: dict) -> tuple:
    """Every AcceleRATE type a card can have with each of Acceleration, Agility and Strength somewhere
    between lo and hi (the thresholds in accelerate.classify). Controlled (and no type) is always kept."""
    out = [acc_mod.CONTROLLED, None]
    if p.accelerate_source:
        out.append(p.accelerate_source)
    try:
        agi0, agi1 = lo["agility"], hi["agility"]
        st0, st1 = lo["strength"], hi["strength"]
        ac1 = hi["acceleration"]
    except KeyError:
        return (acc_mod.EXPLOSIVE, acc_mod.CONTROLLED, acc_mod.LENGTHY, None)
    sex = "female" if p.gender == "F" else "male"
    ex, le = rules["explosive"], rules["lengthy"]
    h = p.height_cm
    if h is None:   # without height classify never says Explosive or Lengthy (the card's own type is used)
        return tuple(dict.fromkeys(out))
    if (h <= ex["max_height_cm"][sex]) and agi1 >= ex["min_agility"] \
            and agi1 - st0 >= ex["min_agility_minus_strength"] and ac1 >= ex["min_acceleration"]:
        out.append(acc_mod.EXPLOSIVE)
    if h >= le["min_height_cm"][sex] and st1 >= le["min_strength"] \
            and st1 - agi0 >= le["min_strength_minus_agility"] and ac1 >= le["min_acceleration"]:
        out.append(acc_mod.LENGTHY)
    return tuple(dict.fromkeys(out))


class FastRater:
    """The IGR rate() gives in one position, without building the full result.
    Same formulas as model.rate / rate_group (tests check that they agree);
    everything that cannot change through evos is worked out once per card."""

    def __init__(self, p: Player, group: str, cfg: dict):
        from .model import body_type_adjust, gk_height_adjust, height_adjust
        from .runs import short_body_value
        from .schema import norm_work_rate
        w, ps_cfg = cfg["weights"], cfg["playstyles"]
        self.p, self.g = p, group
        bl = w["blend"][group]
        self.b_skill, self.b_feel, self.b_pace, self.b_run = bl["skill"], bl["feel"], bl["pace"], bl.get("run") or 0.0
        self.b_stop = bl.get("stop") or 0.0
        hs = w.get("hard_to_stop")
        self.hs = hs if hs and group != "GK" and p.position != "GK" else None
        if self.hs:
            self.hs_ball = {k: v for k, v in _clean(hs["ball"]).items() if v}
            self.hs_run = {k: v for k, v in _clean(hs["run"]).items() if v}
        f = w["feel"]
        self.feel_w = _clean(f["attributes"])
        self.feel_tot = sum(self.feel_w.values())
        from .body import is_lean
        self.feel_h = height_adjust(p, f["height"], is_lean(p, w.get("body_profile")))
        self.feel_b = body_type_adjust(p, f["body_type"])
        self.feel_acc = f["accelerate"]
        self.acc_rules = w["accelerate_rules"]
        pc = w["pace"]
        self.share = pc["acceleration_share"].get(group, pc["acceleration_share"]["default"])
        self.pace_acc = pc["accelerate"]
        self.skill_w = _clean(w["skill"][group])
        self.skill_tot = sum(self.skill_w.values())
        tbl, relc = ps_cfg["playstyles"], ps_cfg["category_relevance"]
        self.ps = {}
        for name, e in tbl.items():
            if str(name).startswith("_") or not isinstance(e, dict) or "category" not in e:
                continue
            rel = (e.get("relevance") or relc[e["category"]]).get(group, 0.0)
            self.ps[name] = (e["base"] * rel, e["plus"] * rel, e.get("synergy", []), e.get("dampen"))
        self.syn = ps_cfg["synergy"]
        self.factors = ps_cfg["diminishing"]["factors"]
        self.ps_max = ps_cfg["diminishing"]["max_total"]
        rc = w["roles"]
        self.role_pos, self.role_pts = rc["group_positions"].get(group, []), rc["points"]
        self.wf_pts, self.wf_f = w["weak_foot"]["points"], w["weak_foot"]["group_factor"].get(group, 0.0)
        self.sm_pts, self.sm_f = w["skill_moves"]["points"], w["skill_moves"]["group_factor"].get(group, 0.0)
        self.gk = gk_height_adjust(p, w) if group == "GK" else 0.0
        self.ob = w.get("off_balance")
        self.ob_f = (self.ob or {}).get("group_factor", {}).get(group, 0.0)
        self.obd_w = _obd_weights(cfg)
        self.obd_off = None
        if p.off_balance_dribbling is not None:
            before = acc_mod.off_balance_dribbling(p.attributes, self.obd_w)
            self.obd_off = (p.off_balance_dribbling, before)
        st = w.get("stand_tackle_tiers")
        self.st_f = (st or {}).get("group_factor", {}).get(group, 0.0) if st else 0.0
        from .body import BodyCard
        self.body = BodyCard(p, group, w.get("body_profile"))   # body type: fixed per card, the agility part moves with evos
        self.st_tiers = st["tiers"] if st else []
        run = w.get("run_ai")
        self.run_w = {k: v for k, v in _clean(run["weights"]).items() if v} if run else {}
        dk = set(run.get("decision_features", ["positioning", "reactions", "arbeidsrate"])) if run else set()
        self.run_dec = {k: v for k, v in self.run_w.items() if k in dk}
        self.run_exe = {k: v for k, v in self.run_w.items() if k not in dk}
        self.run_const = {}
        if run:
            hb = short_body_value(p.height_cm, run)
            if hb is not None:
                self.run_const["kort_kropp"] = hb
            wr = norm_work_rate(p.work_rate_att)
            if wr:
                self.run_const["arbeidsrate"] = float(_clean(run["work_rate_values"])[wr])

    def _weighted(self, a: Dict[str, float], wts: Dict[str, float], tot: float) -> Optional[float]:
        # sum() like model.weighted (Python 3.12+ sums floats with compensation, a loop would not match)
        present = [(a[k], v) for k, v in wts.items() if k in a]
        got = sum(v for _, v in present)
        return sum(x * v for x, v in present) / got if got > 0 else None

    def _run_score(self, a: Dict[str, float], f: Dict[str, float], weights: Dict[str, float]) -> Optional[float]:
        """runs.score over these weights (features in f, else the attribute)."""
        wts = {k: v for k, v in weights.items() if k in f or a.get(k)}
        tot = sum(wts.values())
        if not wts or tot < 0.5 * sum(weights.values()):
            return None
        parts = sorted((round((f[k] if k in f else float(a[k])) * v / tot, 2) for k, v in wts.items()), reverse=True)
        return round(sum(parts), 1)

    def stop(self, a: Dict[str, float], acc_type: Optional[str], ps, psp):
        """stop.scores for these attributes: (score, med ball, uten ball)."""
        from .stop import ps_bonus
        hs = self.hs
        f = {}
        if a.get("sprint_speed") and a.get("strength"):
            f["rask_sterk"] = min(float(a["sprint_speed"]), float(a["strength"]))
        ball0 = self._run_score(a, f, self.hs_ball)
        run0 = self._run_score(a, f, self.hs_run)
        if ball0 is None or run0 is None:
            return None, None, None
        ball = round(ball0 + ps_bonus(hs.get("playstyles_ball"), ps, psp, hs.get("ps_cap_ball", 4.0)), 1)
        run = round(run0 + _acc_off(_clean(hs.get("accelerate_run")), acc_type)
                    + ps_bonus(hs.get("playstyles_run"), ps, psp, hs.get("ps_cap_run", 1.5)), 1)
        share = hs.get("ball_share", 0.5)
        return round(share * ball + (1 - share) * run, 1), ball, run

    def obd(self, a: Dict[str, float]) -> Optional[float]:
        """Off-Balance Dribbling of these attributes (a value from the card data moves with the attributes)."""
        if self.obd_off is not None:
            data, before = self.obd_off
            after = acc_mod.off_balance_dribbling(a, self.obd_w)
            return round(data + after - before, 1) if before is not None and after is not None else data
        return acc_mod.off_balance_dribbling(a, self.obd_w)

    def igr(self, st: State) -> float:
        return self._calc(st, False)

    def detail(self, st: State, acc: Optional[str] = "", ub_ps: Optional[tuple] = None) -> dict:
        """IGR plus the parts Evo Lab shows: feel, pace, Løps-AI (vilje/effekt) and AcceleRATE.
        For the plan search's upper bound: acc forces an AcceleRATE type ("" = the card's own), and
        ub_ps = (most PlayStyles the card can end with, the ones it has): PlayStyles count at full value
        (no dampening), the ones it has always, and of the others only the most valuable that fit.""" 
        return self._calc(st, True, acc, ub_ps)

    def _calc(self, st: State, detail: bool, acc: Optional[str] = "", ub_ps: Optional[tuple] = None):
        a = st.attrs
        p = self.p
        if acc != "":
            acc_type = acc
        else:
            acc_type, _ = acc_mod.classify(a, p.height_cm, p.gender, self.acc_rules)
            if acc_type is None and p.accelerate_source:
                acc_type = p.accelerate_source
        out = {"acc": acc_type} if detail else None
        skill = self._weighted(a, self.skill_w, self.skill_tot)
        feel = run = pace = None
        if self.b_feel or detail:
            base = self._weighted(a, self.feel_w, self.feel_tot)
            if base is not None:
                feel = base + self.feel_h + _acc_off(self.feel_acc, acc_type) + self.feel_b
        if (self.b_pace or detail) and self.g != "GK":
            ac, sp = a.get("acceleration"), a.get("sprint_speed")
            if ac is not None or sp is not None:
                ac = sp if ac is None else ac
                sp = ac if sp is None else sp
                pace = self.share * ac + (1 - self.share) * sp + _acc_off(self.pace_acc, acc_type)
        if self.run_w and (self.b_run or detail):
            f = dict(self.run_const)
            if "agility" in a and "strength" in a and a["agility"] and a["strength"]:
                f["kvikk_sterk"] = min(a["agility"], a["strength"])
            if "balance" in a and "strength" in a and a["balance"] and a["strength"]:
                f["balanse_sterk"] = min(a["balance"], a["strength"])
            run = self._run_score(a, f, self.run_w)
            if detail:
                out["vil"] = self._run_score(a, f, self.run_dec) if self.run_dec else None
                out["eff"] = self._run_score(a, f, self.run_exe) if self.run_exe else None
        stp = None
        if self.hs and (self.b_stop or detail):
            stp, stb, stl = self.stop(a, acc_type, st.ps, st.psp)
            if detail:
                out.update(stp=stp, stb=stb, stl=stl)
        if detail:
            out.update(feel=round(feel, 1) if feel is not None else None, pace=round(pace, 1) if pace is not None else None,
                       run=run)
        if skill is None:
            if detail:
                out["igr"] = 0.0
                return out
            return 0.0
        core, used = self.b_skill * skill, self.b_skill
        if self.b_feel and feel is not None:
            core += self.b_feel * feel
            used += self.b_feel
        if self.b_pace and pace is not None:
            core += self.b_pace * pace
            used += self.b_pace
        if self.b_run and run is not None:
            core += self.b_run * run
            used += self.b_run
        if self.b_stop and stp is not None:
            core += self.b_stop * stp
            used += self.b_stop
        core /= used
        items = []
        extra = []
        fixed = ub_ps[1] if ub_ps is not None else None
        for names, plus in ((st.psp, True), (st.ps, False)):
            for n in names:
                e = self.ps.get(n)
                if not e:
                    continue
                keys = e[2]
                vals = [a[k] for k in keys if k in a]
                if vals:
                    s = self.syn
                    syn = max(s["min"], min(s["max"], (sum(vals) / len(vals) - s["floor"]) / s["span"]))
                else:
                    syn = 0.6
                damp = 1.0
                d = e[3]
                if d and d["attribute"] in a and ub_ps is None:
                    t = max(0.0, min(1.0, (a[d["attribute"]] - d["from"]) / (d["to"] - d["from"])))
                    damp = 1.0 - (1.0 - d["min_factor"]) * t
                v = (e[1] if plus else e[0]) * syn * damp
                if fixed is not None and n not in fixed:
                    extra.append(v)   # can still come; the ones the card has stay
                else:
                    items.append(v)
        if ub_ps is not None:
            extra.sort(reverse=True)
            items += extra[:max(0, ub_ps[0] - len(fixed))]
        items.sort(reverse=True)
        fs = self.factors
        ps_total = 0.0
        for i, x in enumerate(items):  # a plain loop, like model.playstyle_bonus
            ps_total += x * (fs[i] if i < len(fs) else fs[-1])
        igr = core + min(ps_total, self.ps_max)
        best = -1
        for pos in self.role_pos:
            for lvl in (st.roles.get(pos) or {}).values():
                best = max(best, lvl)
        if best >= 0:
            igr += self.role_pts.get(str(best), 0.0)
        if st.wf is not None:
            igr += self.wf_pts.get(str(st.wf), 0.0) * self.wf_f
        if st.sm is not None:
            igr += self.sm_pts.get(str(st.sm), 0.0) * self.sm_f
        igr += self.gk
        if (self.ob and self.ob_f) or detail:
            obd = self.obd(a)
            if detail:
                out["obd"] = obd
            if obd is not None and self.ob and self.ob_f:
                c = self.ob
                igr += max(0.0, min(c["max"], (obd - c["start"]) * c["per_point"])) * self.ob_f
        if self.st_f:
            v = a.get("standing_tackle")
            if v is not None:
                pts = 0.0
                for threshold, val in self.st_tiers:
                    if v >= threshold:
                        pts = val
                igr += pts * self.st_f
        if self.body.on:
            # upper bound for the plan search: every body + PlayStyle combo the card could still get counts
            bp = self.body.upper(a) if ub_ps is not None else self.body.points(a, st.ps, st.psp)
            igr += bp
            if detail:
                out["body"] = round(bp, 2)
        if detail:
            out["igr"] = round(igr, 1)
            return out
        return round(igr, 1)


class Evaluator:
    """IGR of a state in one position (fast path), and the full result when the details are needed."""

    def __init__(self, p: Player, group: str, cfg: dict, rules: dict):
        self.p, self.g, self.cfg, self.rules, self.memo = p, group, cfg, rules, {}
        self.fast = FastRater(p, group, cfg)
        self.calls = 0

    def full(self, st: State) -> dict:
        self.calls += 1
        return rate(to_player(self.p, st, self.rules, self.cfg), self.cfg, groups=[self.g])

    def igr(self, st: State, memo: bool = False) -> float:
        k = st.key() if memo else None
        if k is not None and k in self.memo:
            return self.memo[k]
        self.calls += 1
        v = self.fast.igr(st)
        if k is not None:
            self.memo[k] = v
        return v


# ---------------------------------------------------------------- live chain

def _changes(a: State, b: State) -> dict:
    d = [[k, round(a.attrs[k]), round(b.attrs[k])] for k in b.attrs if k in a.attrs and round(b.attrs[k]) != round(a.attrs[k])]
    d.sort(key=lambda x: x[2] - x[1], reverse=True)
    return {"d": d, "ovr": [a.ovr, b.ovr], "ps": [x for x in b.ps if x not in a.ps and x not in a.psp],
            "psp": [x for x in b.psp if x not in a.psp], "wf": [a.wf, b.wf] if a.wf != b.wf else None,
            "sm": [a.sm, b.sm] if a.sm != b.sm else None}


NEAR = {"ovr": 2, "pace": 5, "ps": 2, "psp": 1}


def _first_block(e: dict, st: State, rules: dict) -> Optional[str]:
    """Why an evo is closed at the end of the plan, PlayStyle limits first (they usually bind first,
    since PlayStyle evos are taken early)."""
    r = e["req"]
    if r["max_ps"] is not None and ps_count(st, rules) > r["max_ps"]:
        return f"{ps_count(st, rules)} PlayStyles (maks {r['max_ps']})"
    if r["max_psp"] is not None and len(st.psp) > r["max_psp"]:
        return f"{len(st.psp)} PlayStyle+ (maks {r['max_psp']})"
    why = check(e, st, rules)
    return why[1] if why else None


def _close(e: dict, st: State, cat: str, rules: dict) -> bool:
    """Only just outside the evo (a near miss worth knowing about)?"""
    r = e["req"]
    if cat == "ovr" and r["max_ovr"] is not None:
        return st.ovr - r["max_ovr"] <= NEAR["ovr"]
    if cat == "pace" and r["max_pace"] is not None:
        pac = face_value(st.attrs, "pace", rules)
        return pac is not None and pac - r["max_pace"] <= NEAR["pace"]
    if cat == "ps" and r["max_ps"] is not None:
        return ps_count(st, rules) - r["max_ps"] <= NEAR["ps"]
    if cat == "psp" and r["max_psp"] is not None:
        return len(st.psp) - r["max_psp"] <= NEAR["psp"]
    return False


ACC_RANK = {"Explosive": 2, "Controlled": 1, "Lengthy": 0}


def gates(d0: dict, d1: dict, a0: Dict[str, float], a1: Dict[str, float], g: str, cfg: dict) -> List[List]:
    """Game thresholds an upgrade crosses: [kind, text, good]. AcceleRATE changes (also the bad ones),
    Off-Balance Dribbling reaching the level where it kicks in, and Standing Tackle animation tiers."""
    w = cfg["weights"]
    out = []
    if d0.get("acc") != d1.get("acc") and d1.get("acc"):
        good = ACC_RANK.get(d1["acc"], 1) > ACC_RANK.get(d0.get("acc") or "", 1)
        out.append(["acc", f"AcceleRATE {d0.get('acc') or '?'} → {d1['acc']}", good])
    start = (w.get("off_balance") or {}).get("start")
    o0, o1 = d0.get("obd"), d1.get("obd")
    if start is not None and o0 is not None and o1 is not None and o0 < start <= o1:
        out.append(["obd", f"Off-balance dribbling {o0:.0f} → {o1:.0f} (kommer inn fra {start})", True])
    st = w.get("stand_tackle_tiers") or {}
    if st and st.get("group_factor", {}).get(g):
        s0, s1 = a0.get("standing_tackle"), a1.get("standing_tackle")
        for thr, _ in st.get("tiers", []):
            if thr and s0 is not None and s1 is not None and s0 < thr <= s1:
                out.append(["st", f"Standing Tackle {s0:.0f} → {s1:.0f} (flere taklingsanimasjoner fra {thr})", True])
    return out


def _plan_orders(cands: List[dict]) -> List[List[dict]]:
    """Orders to walk the evos in. Evos only raise a card, and the requirements are maximums, so the
    evo with the strictest limit goes first; three tie-breaks cover OVR, PlayStyles and pace limits.
    An evo that needs another evo first is moved right after it. Each evo appears once."""
    lim = lambda e, k: e["req"][k] if e["req"][k] is not None else 99
    keys = [lambda e: (lim(e, "max_ovr"), lim(e, "max_ps"), lim(e, "max_pace")),
            lambda e: (lim(e, "max_ps"), lim(e, "max_ovr"), lim(e, "max_pace")),
            lambda e: (lim(e, "max_pace"), lim(e, "max_ovr"), lim(e, "max_ps"))]
    out = []
    for kf in keys:
        order = sorted(cands, key=lambda e: (kf(e), e["key"]))
        for e in list(order):  # prerequisites first
            pre = e["req"]["requires_evo"]
            i = next((j for j, x in enumerate(order) if x["key"] == pre), None)
            if i is not None and i > order.index(e):
                order.remove(e)
                order.insert(i, e)
        # each evo once per card (repeatable = more players), or per_card times in a row when the same card may
        # take it again
        seq = [x for e in order for x in [e] * e.get("per_card", 1)]
        if seq not in out:
            out.append(seq)
    return out


def defense_cfg(rules: dict) -> dict:
    return rules.get("defense") or {}


def def_value(attrs: Dict[str, float], group: str, rules: dict) -> Optional[float]:
    """Forsvar: weighted defensive attributes for CB, backs and CDM (the same as defOf on the page, unrounded).
    None for other positions or when an attribute is missing."""
    w = _clean((defense_cfg(rules).get("weights") or {}).get(group) or {})
    if not w:
        return None
    tot = num = 0.0
    for k, x in w.items():  # a plain loop in the file's order, like the page
        if attrs.get(k) is None:
            return None
        num += attrs[k] * x
        tot += x
    return num / tot if tot else None


def _attack_ps(u: dict, bad: set) -> bool:
    return any(n in bad for n, _c in u.get("ps", [])) or any(n in bad for n, _c in u.get("psp", []))


def _gives_more(u: dict, bad: set) -> bool:
    """Does the upgrade give anything besides attacking PlayStyles?"""
    return bool(u.get("ovr") or u.get("wf") or u.get("sm") or u.get("stats") or u.get("face") or u.get("roles")
                or any(n not in bad for n, _c in u.get("ps", [])) or any(n not in bad for n, _c in u.get("psp", [])))


def plan_paths(evo: dict, group: str, rules: dict) -> list:
    """The pathway options the live plan may choose for a card in this position ([None] = no options).
    CB, backs and CDM never choose an attacking PlayStyle such as Gamechanger: an option with one is dropped
    when another option has none, and an evo that only gives attacking PlayStyles is not taken at all
    (an empty list). If every option has one but also gives something else, the evo is still taken."""
    paths = list(evo["up"]["paths"] or [None])
    dc = defense_cfg(rules)
    if group not in (dc.get("groups") or []):
        return paths
    bad = set(dc.get("attack_playstyles") or [])
    up = evo["up"]
    clean = [p for p in paths if not (p and _attack_ps(p, bad))]
    if clean and not _attack_ps(up, bad):
        return clean
    return [p for p in (clean or paths) if _gives_more(up, bad) or (p is not None and _gives_more(p, bad))]


def search_ends(st0: State, cands: List[dict], rules: dict, max_nodes: int = 20000,
                best_path=None, key=None, paths_of=None) -> Dict[tuple, Tuple[State, list]]:
    """Every combination of the live evos the card can take: for each evo in turn, take it (every pathway
    option) or skip it. Skipping matters: an evo that lifts OVR can shut the card out of a better one later.
    A skipped evo that the card can still enter at the end is taken then (skipping it gains nothing), so only
    end states where no evo is left are kept. Same card states are merged.
    Returns {state key: (end state, steps)}. key(state) decides which states count as the same (by default
    State.key; plan_live passes one that only looks at what the rating uses). paths_of(evo) gives the
    pathway options that may be chosen (plan_paths); an empty list means the evo is not taken."""
    skey = key or (lambda x: x.key())
    paths_of = paths_of or (lambda e: list(e["up"]["paths"] or [None]))
    ends: Dict[tuple, Tuple[State, list]] = {}
    nodes = 0

    def finish(st: State, chain: list, skipped: tuple) -> Tuple[State, list]:
        moved = bool(skipped)
        while moved:
            moved = False
            for e in skipped:
                allowed = paths_of(e)
                if not allowed or check(e, st, rules) is not None:
                    continue
                path = best_path(e, st, allowed) if (best_path and e["up"]["paths"]) else allowed[0]
                nxt = apply(e, st, rules, path)
                if skey(nxt) == skey(st):
                    continue
                chain = chain + [(e, path, st, nxt)]
                st, moved = nxt, True
        return st, chain
    pace_keys = set(_clean(rules["face"]["pace"]))

    def effects(e: dict) -> set:
        """What an evo can raise that later requirements limit."""
        out = set()
        for u in [e["up"]] + list(e["up"]["paths"] or []):
            if u.get("ovr"):
                out.add("ovr")
            if pace_keys & set(u.get("stats") or {}) or "pace" in (u.get("face") or {}):
                out.add("pace")
            if u.get("ps"):
                out.add("ps")
            if u.get("psp"):
                out.update(("ps", "psp"))
        return out

    limit_of = {"ovr": "max_ovr", "pace": "max_pace", "ps": "max_ps", "psp": "max_psp"}
    # two passes: first a quick one that only skips an evo when it would shut the card out of a later evo
    # right away, then a wide one that may skip any evo that can lift OVR, pace or PlayStyles (with a node budget)
    for strict, order in [(True, o) for o in _plan_orders(cands)] + [(False, o) for o in _plan_orders(cands)]:
        seen = set()
        n = len(order)
        # skipping an evo only helps if it can shut out a later evo (its OVR, pace or PlayStyles)
        may_skip = []
        for i, e in enumerate(order):
            eff = effects(e)
            may_skip.append(any(order[j]["req"][limit_of[x]] is not None for j in range(i + 1, n) for x in eff
                                if order[j]["key"] != e["key"]))

        def blocks_later(i: int, st: State, nexts: List[State]) -> bool:
            """Would taking order[i] now shut the card out of a later evo it could still enter?"""
            for j in range(i + 1, n):
                ej = order[j]
                if ej["key"] == order[i]["key"]:
                    continue
                now = check(ej, st, rules)
                if now is not None and now[0] not in ("pre", "done") and not (now[0] == "ovr" and ej["req"]["min_ovr"] is not None
                                                                          and st.ovr < ej["req"]["min_ovr"]):
                    continue
                for nxt in nexts:
                    why = check(ej, nxt, rules)
                    if why is not None and why[0] in ("ovr", "pace", "ps", "psp"):
                        return True
            return False

        def rec(i: int, st: State, sk: tuple, done: tuple, chain: list, skipped: tuple) -> None:
            nonlocal nodes
            k = (i, sk, done)
            if k in seen or (not strict and nodes >= max_nodes) or (strict and len(seen) >= 4 * max_nodes):
                return
            seen.add(k)
            if not strict:
                nodes += 1
            if i == n:
                st2, chain2 = finish(st, chain, skipped)
                k2 = skey(st2) if chain2 is not chain else sk
                old = ends.get(k2)
                if old is None or len(chain2) < len(old[1]):
                    ends[k2] = (st2, chain2)
                return
            e = order[i]
            allowed = paths_of(e)
            if allowed and check(e, st, rules) is None:
                nexts = []
                for path in allowed:
                    nxt = apply(e, st, rules, path)
                    nk = skey(nxt)
                    if nk != sk:
                        nexts.append((path, nxt, nk))
                if nexts:
                    done2 = tuple(sorted(done + (e["key"],)))
                    for path, nxt, nk in nexts:
                        rec(i + 1, nxt, nk, done2, chain + [(e, path, st, nxt)], skipped)
                    if may_skip[i] and (not strict or blocks_later(i, st, [x for _, x, _ in nexts])):
                        rec(i + 1, st, sk, done, chain, skipped + (e,))
                else:
                    rec(i + 1, st, sk, done, chain, skipped)
            else:
                rec(i + 1, st, sk, done, chain, skipped)

        rec(0, st0, skey(st0), tuple(sorted(st0.done)), [], ())
    if not ends:
        ends[skey(st0)] = (st0, [])
    return ends


PLAN_METRICS = ("igr", "run", "feel", "stp", "def")
ACC_TYPES = (acc_mod.EXPLOSIVE, acc_mod.CONTROLLED, acc_mod.LENGTHY, None)


def _gather(rest: List[dict], paths_of, rules: dict) -> dict:
    """What the remaining evos can give at most, summed over evos (each evo: its shared levels plus, per
    attribute, the best of its options)."""
    gain: Dict[str, float] = {}
    top: Dict[str, float] = {}
    ovr, wf, sm = [], [], []
    psp_names, ps_names = set(), set()
    roles: List[tuple] = []
    face_opts: List[tuple] = []   # (evo's place in rest, [(main stat, gain, max), ...]) per option
    for ei, e in enumerate(rest):   # an evo the card may take twice is in rest twice
        opts = [p for p in (paths_of(e) or []) if p] or [None]
        eg: Dict[str, float] = {}
        ec: Dict[str, float] = {}
        for path in opts:
            parts = [e["up"]] + ([path] if path else [])
            pg: Dict[str, float] = {}
            fopt = []
            for u in parts:
                for k, (g, c) in u["stats"].items():
                    pg[k] = pg.get(k, 0.0) + max(0.0, g)
                    ec[k] = max(ec.get(k, 0.0), c)
                for which, (g, c) in u["face"].items():
                    fopt.append((which, max(0.0, g), c))
                for n, _c in u["ps"]:
                    ps_names.add(n)
                for n, _c in u["psp"]:
                    psp_names.add(n)
                roles.extend(u["roles"])
            if fopt:
                face_opts.append((ei, fopt))
            for k, v in pg.items():
                eg[k] = max(eg.get(k, 0.0), v)
            for lst, attr in ((ovr, "ovr"), (wf, "wf"), (sm, "sm")):
                g = sum(max(0, u[attr][0]) for u in parts if u[attr])
                c = max([u[attr][1] for u in parts if u[attr]], default=None)
                if c is not None:
                    lst.append((g, c))
        for k, v in eg.items():
            gain[k] = gain.get(k, 0.0) + v
        for k, c in ec.items():
            top[k] = max(top.get(k, 0.0), c)
    face_keys = {k for _e, opts in face_opts for (w, _g, _c) in opts for k in _clean(rules["face"][w])}
    return {"gain": gain, "top": top, "face_opts": face_opts, "ovr": ovr, "wf": wf, "sm": sm,
            "ps": ps_names, "psp": psp_names, "roles": roles, "keys": sorted(set(gain) | face_keys)}


def _optimistic(st: State, rest: List[dict], paths_of, rules: dict, gathered: Optional[dict] = None) -> State:
    """A card at least as good as anything the remaining evos can make of st, in every rating: each
    attribute raised by every remaining evo (its shared levels plus the best of its options for that
    attribute; no requirements, no order). A plain upgrade leaves an attribute at most at max(before, its
    max) and a main-stat upgrade adds at most its gain, so an attribute ends at most at max(now, highest
    max) + all main-stat gains, and at most now + every gain. Also all their PlayStyles, and the most OVR,
    weak foot, skill moves and roles they can give."""
    g = gathered or _gather(rest, paths_of, rules)
    s = st.copy()
    gain, top = g["gain"], g["top"]
    # a main-stat upgrade «+g up to c» adds at most min(g, c - the main stat now) (main stats only go up);
    # per evo the best of its options, summed over the evos
    face_now: Dict[str, Optional[float]] = {}
    by_evo: Dict[str, Dict[str, float]] = {}
    for ekey, opts in g["face_opts"]:
        per: Dict[str, float] = {}
        for which, gn, cap in opts:
            if which not in face_now:
                face_now[which] = face_value(st.attrs, which, rules)
            now = face_now[which]
            add = gn if now is None else max(0.0, min(gn, cap - now))
            if add > 0:
                for k in _clean(rules["face"][which]):
                    per[k] = per.get(k, 0.0) + add
        best = by_evo.setdefault(ekey, {})
        for k, v in per.items():
            best[k] = max(best.get(k, 0.0), v)
    face_gain: Dict[str, float] = {}
    for per in by_evo.values():
        for k, v in per.items():
            face_gain[k] = face_gain.get(k, 0.0) + v
    for k in g["keys"]:
        if k not in s.attrs:
            continue
        cur = s.attrs[k]
        fg = face_gain.get(k, 0.0)
        hi = min(cur + gain.get(k, 0.0) + fg, max(cur, top.get(k, cur)) + fg)
        s.attrs[k] = min(99.0, max(cur, hi))

    def up_to(cur, pairs):
        if cur is None or not pairs:
            return cur
        return int(min(cur + sum(x for x, _ in pairs), max([cur] + [c for _, c in pairs])))
    s.ovr, s.wf, s.sm = up_to(s.ovr, g["ovr"]), up_to(s.wf, g["wf"]), up_to(s.sm, g["sm"])
    psp = set(s.psp) | g["psp"]
    s.ps, s.psp = sorted((set(s.ps) | g["ps"]) - psp), sorted(psp)
    for pos, role, level in g["roles"]:
        cur = s.roles.setdefault(pos, {})
        cur[role] = max(cur.get(role, 0), level)
    return s


def _touched(e: dict, rules: dict) -> set:
    """Attributes the evo (any of its options, also those a position never picks) can raise."""
    r = set()
    for u in [e["up"]] + [x for x in (e["up"]["paths"] or []) if x]:
        r.update(u["stats"])
        for which in u["face"]:
            r.update(_clean(rules["face"][which]))
    return r


def ps_limit(st: State, rest: List[dict], paths_of, ps_cap: int) -> int:
    """The most PlayStyles (with +) the card can end with. A PlayStyle «(N)» in an evo is only added while the
    card has fewer than N, and an evo with «max N PlayStyles» is only entered with N or fewer; so after the
    last PlayStyle added the card has at most the lowest of those, and never more than the cap."""
    now = len(st.ps) + len(st.psp)
    hi = now
    for e in rest:
        lim = e["req"]["max_ps"]
        for x in (paths_of(e) or [None]):
            parts = [e["up"]] + ([x] if x else [])
            add = sum(len(u["ps"]) + len(u["psp"]) for u in parts)
            for u in parts:
                for _n, c in list(u["ps"]) + list(u["psp"]):
                    top = ps_cap if c is None else min(int(c), ps_cap)
                    if lim is not None:
                        top = min(top, lim + add)
                    hi = max(hi, top)
    return min(hi, ps_cap)


def search_best(st0: State, cands: List[dict], rules: dict, score, bound, key, paths_of,
                seeds: Optional[List[Tuple[State, list]]] = None, max_nodes: Optional[int] = None):
    """The best plan for every rating, found by trying every way to use the evos: any evo the card can
    enter, in any order, with any of its options, stopping anywhere. Card states reached twice are only
    gone on from once (with the shortest way there). A branch is left only when a safe upper bound shows
    nothing below it can beat, or tie with fewer evos, the best plan found for any of the ratings.
    score(state) -> {metric: value}; bound(state, remaining evos) -> {metric: value at least as high as
    any state below}. seeds are plans found another way (a good start). Returns ({metric: (value, igr,
    steps, premium, state, chain)}, nodes visited, complete)."""
    pre_needed = {e["req"]["requires_evo"] for e in cands if e["req"]["requires_evo"]}
    best: Dict[str, tuple] = {}
    acc_inputs = {"acceleration", "agility", "strength"}   # what AcceleRATE is worked out from (with height)
    pace_attrs = set(_clean(rules["face"]["pace"]))
    touches: Dict[str, set] = {}
    limits: Dict[str, set] = {}
    for e in cands:
        r = set()
        for u in [e["up"]] + [x for x in (paths_of(e) or []) if x]:
            r.update(u["stats"])
            for which in u["face"]:
                r.update(_clean(rules["face"][which]))
            for x in ("ovr", "wf", "sm"):
                if u[x]:
                    r.add(x)
            if u["ps"] or u["psp"]:
                r.add("ps")
        touches[e["key"]] = r
        q = e["req"]
        lim = set()
        if q["max_ovr"] is not None or q["min_ovr"] is not None:
            lim.add("ovr")
        if q["max_pace"] is not None:
            lim |= pace_attrs
        if q["max_ps"] is not None or q["max_psp"] is not None:
            lim.add("ps")
        limits[e["key"]] = lim

    def free(e: dict, rest: List[dict]) -> bool:
        """Taking e now is never worse than any other use of it: it touches nothing another remaining evo
        upgrades or is limited by (so the others can still be taken, in any order, with the same result),
        and nothing AcceleRATE comes from (so every rating only goes up with it)."""
        r = touches[e["key"]]
        if r & acc_inputs:
            return False
        return not any(o is not e and (r & touches[o["key"]] or r & limits[o["key"]]) for o in rest)

    def offer(st: State, chain: list, sc: dict) -> None:
        cost = (len(chain), sum(1 for c in chain if c[0]["premium"]))
        for m in PLAN_METRICS:
            v = sc.get(m)
            if v is None:
                continue
            cand = (v, sc["igr"], -cost[0], -cost[1])
            old = best.get(m)
            if old is None or cand > old[0]:
                best[m] = (cand, st, chain)

    def hopeless(ub: dict, n_steps: int, prem: int) -> bool:
        """Nothing below can beat the best plan for any rating (value, then IGR, then fewer evos)."""
        for m in PLAN_METRICS:
            v = ub.get(m)
            if v is None:
                continue
            old = best.get(m)
            if old is None:
                return False
            if v > old[0][0] + 1e-9:   # a tie is not worth going on for: trim() drops steps that add nothing
                return False
        return True

    for st, chain in seeds or []:
        offer(st, chain, score(st))
    seen: Dict[tuple, List[Tuple[frozenset, int]]] = {}
    nodes = 0
    complete = True
    stack = [(st0, tuple(sorted(st0.done)), [])]
    while stack:
        st, done, chain = stack.pop()
        # the same card reached before with fewer (or the same) evos used and no more steps: nothing new here
        # (evos as a multiset: one the card may take twice counts once per time taken)
        taken = Counter(done)
        ck, ds = key(st), frozenset((k, i) for k, n in taken.items() for i in range(n))
        prev = seen.setdefault(ck, [])
        if any(d <= ds and n <= len(chain) for d, n in prev):
            continue
        prev.append((ds, len(chain)))
        nodes += 1
        if max_nodes and nodes > max_nodes:
            complete = False
            break
        rest, rest_all = [], []   # rest_all: an evo once per time the card may still take it
        for e in cands:
            left = e.get("per_card", 1) - taken.get(e["key"], 0)
            if left <= 0 or not paths_of(e):
                continue
            why = check(e, st, rules)
            if why is None or why[0] == "pre" or (why[0] == "ovr" and e["req"]["min_ovr"] is not None and st.ovr < e["req"]["min_ovr"]):
                rest.append(e)
                rest_all.extend([e] * left)
        if rest:
            # the bound covers this card too (the evos only add), so a hopeless branch is left unrated
            prem = sum(1 for c in chain if c[0]["premium"])
            if chain and hopeless(bound(st, rest_all), len(chain) - 1, prem):
                continue
        offer(st, chain, score(st))
        if not rest:
            continue
        sk = key(st)
        moves = []   # (evo, [(option, next card)]) for the evos the card can enter now that change something
        for e in rest:
            if check(e, st, rules) is not None:
                continue
            kids = []
            for path in paths_of(e):
                nxt = apply(e, st, rules, path)
                if key(nxt) != sk or e["key"] in pre_needed:
                    kids.append((path, nxt))
            if kids:
                moves.append((e, kids))
        forced = next((m for m in moves if free(m[0], rest)), None)
        for e, kids in ([forced] if forced is not None else moves):
            for path, nxt in kids:
                stack.append((nxt, tuple(sorted(done + (e["key"],))), chain + [(e, path, st, nxt)]))
    return best, nodes, complete


def plan_live(p: Player, st0: State, evos: List[dict], ev: Evaluator, rules: dict, max_nodes: int = 20000,
              quick: bool = False) -> dict:
    """Best order of the live evos for this card, with the evos it misses and why.
    quick: only the fast search (when the run is short of time; the full search is done next run)."""
    cands, near, unchecked = [], [], []
    for e in evos:
        r = e["req"]
        if r["positions"] and not any(x in r["positions"] for x in st0.positions):
            if st0.pos_unsure:
                unchecked.append([e["name"], pos_unsure_text(r)])
            continue
        why = check(e, st0, rules)
        if why and why[0] in ("pos", "age"):
            continue
        if why and why[0] in ("age?", "pos?"):
            unchecked.append([e["name"], why[1]])
            continue
        if e["unchecked"] and not rules.get("include_unchecked", False):
            if why is None or why[0] in ("pre",):
                unchecked.append([e["name"], e["unchecked"]])
            continue
        if why is None and r["max_ps"] is not None and getattr(p, "ps_from_base", False) \
                and ps_count(st0, rules) + 1 > r["max_ps"]:
            # promo cards often get a PlayStyle more than the base card, and we only know the base card's
            n = ps_count(st0, rules)
            unchecked.append([e["name"], f"maks {r['max_ps']} PlayStyles. Basekortet har {n}, og spesialkortet kan ha flere"])
            continue
        if why is None or why[0] in ("pre",) or (why[0] == "ovr" and r["min_ovr"] is not None and st0.ovr < r["min_ovr"]):
            cands.append(e)
        elif why[0] in ("ovr", "pace", "ps", "psp") and _close(e, st0, why[0], rules):
            near.append([e["name"], why[1]])
    names = {e["key"]: e["name"] for e in evos}
    changed = True
    while changed:   # an evo whose earlier step can't be taken goes too (and the one after it, ...)
        changed = False
        keys = {e["key"] for e in cands}
        for e in list(cands):
            pre = e["req"]["requires_evo"]
            if pre and pre not in keys:
                cands.remove(e)
                changed = True
                if any(u[0] in (names.get(pre), names.get(pre, pre)) for u in unchecked) or \
                        any(u[0] == names.get(pre) for u in unchecked):
                    unchecked.append([e["name"], f"etter {names.get(pre, pre)}"])
    role_pos = ev.fast.role_pos

    def rating_key(st: State) -> tuple:  # the same card for the rating: other positions' roles do not count
        lv = max((v for pos in role_pos for v in (st.roles.get(pos) or {}).values()), default=-1)
        return (tuple(st.attrs.values()), st.ovr, tuple(sorted(st.ps)), tuple(sorted(st.psp)), st.wf, st.sm, lv)
    paths_of = lambda e: plan_paths(e, ev.g, rules)
    # short of time: a smaller version of the fast search only (the full search is done next run)
    ends = search_ends(st0, cands, rules, min(max_nodes, QUICK_NODES) if quick else max_nodes, key=rating_key,
                       best_path=lambda e, st, allowed=None: _best_path(e, st, ev.g, ev.cfg, allowed),
                       paths_of=paths_of)
    primary = (p.position or "").upper()
    use_rpp = rules.get("roles_plus_plus", True)

    rated: Dict[tuple, tuple] = {}   # the same card for the rating is rated once

    def rate_end(st: State) -> tuple:
        """(details, the card after Roles++, Roles++ added?) for a plan's end state."""
        k = rating_key(st)
        hit = rated.get(k)
        if hit is None:
            fin, rpp = roles_plus_plus(st, primary) if use_rpp else (st, False)
            d = ev.fast.detail(fin)
            ev.calls += 1
            d["def"] = def_value(fin.attrs, ev.g, rules)
            hit = rated[k] = (d, fin, rpp)
        return hit

    def score(st: State) -> dict:
        d = rate_end(st)[0]
        return {"igr": d["igr"], "run": d.get("run"), "feel": d.get("feel"), "stp": d.get("stp"), "def": d["def"]}

    ps_cap = int(rules.get("ps_cap", 8))
    acc_inputs = {"acceleration", "agility", "strength"}
    moves_acc = {e["key"] for e in cands if acc_inputs & _touched(e, rules)}

    gathered: Dict[tuple, dict] = {}

    def stat_options(e: dict) -> list:
        """The evo's options that differ in attributes (PlayStyle-only choices are covered by the PlayStyle bound)."""
        al = [x for x in (paths_of(e) or []) if x]
        return al if len(al) > 1 and any(x["stats"] or x["face"] for x in al) else []

    def bound(st: State, rest: List[dict]) -> dict:
        n_ps = (ps_limit(st, rest, paths_of, ps_cap), set(st.ps) | set(st.psp))
        moves = any(e["key"] in moves_acc for e in rest)
        # evos with options that give different attributes: the bound for each choice, and the highest of them
        multi = [e for e in rest if stat_options(e)]
        combos = [()]
        if len({e["key"] for e in multi}) < len(multi):
            multi = []   # an evo taken twice may get two different choices: per attribute the best option (safe)
        for e in multi:
            combos = [c + ((e["key"], i),) for c in combos for i in range(len(stat_options(e)))]
            if len(combos) > 24:   # too many: per attribute the best option (still safe, a bit looser)
                combos = [()]
                break
        out: Dict[str, Optional[float]] = {}
        for combo in combos:
            fixed = dict(combo)
            pick = (lambda e, fixed=fixed: [stat_options(e)[fixed[e["key"]]]] if e["key"] in fixed else paths_of(e))
            rk = (tuple(e["key"] for e in rest), combo)
            if rk not in gathered:
                gathered[rk] = _gather(rest, pick, rules)
            hi = _optimistic(st, rest, pick, rules, gathered[rk])
            fin = roles_plus_plus(hi, primary)[0] if use_rpp else hi
            dv = def_value(fin.attrs, ev.g, rules)
            if dv is not None and (out.get("def") is None or dv > out["def"]):
                out["def"] = dv
            # AcceleRATE is the one thing that can go down as stats go up: the best of the types it can still get
            acc = acc_types_possible(st.attrs, fin.attrs, p, ev.fast.acc_rules) if moves else ""
            d = ev.fast.detail(fin, acc, n_ps)
            ev.calls += 1
            for m in ("igr", "run", "feel", "stp"):
                v = d.get(m)
                if v is not None and (out.get(m) is None or v > out[m]):
                    out[m] = v
        return out
    # the old search's plans as a start, then the full search; its best plans are the ones to choose from
    best, nodes, complete = search_best(st0, cands, rules, score, bound, rating_key, paths_of,
                                        seeds=list(ends.values()),
                                        max_nodes=1 if quick else int(rules.get("plan_search_nodes", SEARCH_MAX_NODES)))

    def replay(steps: list) -> Optional[list]:
        st, out = st0, []
        for e, path in steps:
            if check(e, st, rules) is not None:
                return None
            nxt = apply(e, st, rules, path)
            out.append((e, path, st, nxt))
            st = nxt
        return out

    def trim(chain: list, m: str) -> list:
        # Leave out evos that add nothing: a plan without one is kept when it is still allowed and is at
        # least as good for this rating and for IGR (ties are not searched further, so this picks the
        # shortest of equally good plans).
        if not chain:
            return chain
        ref = score(chain[-1][3])
        changed = True
        while changed:
            changed = False
            for i in range(len(chain)):
                cand = replay([(c[0], c[1]) for j, c in enumerate(chain) if j != i])
                if cand is None:
                    continue
                s2 = score(cand[-1][3]) if cand else score(st0)
                if (s2.get(m) is None or ref.get(m) is None or s2[m] >= ref[m] - 1e-9) and s2["igr"] >= ref["igr"] - 1e-9:
                    chain, changed = cand, True
                    break
        return chain
    ends = dict(ends)
    for m, (_c, st, chain) in best.items():
        chain = trim(chain, m)
        ends[("best", m)] = (chain[-1][3] if chain else st0, chain)
    # the best end state for IGR, and also for Løps-AI and for feel (often the same plan)
    scored = []
    for st, chain in ends.values():
        d, fin, rpp = rate_end(st)   # with Forsvar for CB, backs and CDM (the plan for «best forsvar»)
        cost = (len(chain), sum(1 for c in chain if c[0]["premium"]))
        scored.append((d, fin, chain, cost, rpp, st))

    def pick(metric):
        return max(scored, key=lambda t: ((t[0].get(metric) if t[0].get(metric) is not None else -1), t[0]["igr"],
                                          -t[3][0], -t[3][1]))
    best = pick("igr")
    d_best, fin, chain, _, rpp, last = best
    v = d_best["igr"]
    alt = {}
    for metric in ("run", "feel", "stp", "def"):
        o = pick(metric)
        seq = [[c[0]["key"], (c[1] or {}).get("label", "")] for c in o[2]]
        if seq != [[c[0]["key"], (c[1] or {}).get("label", "")] for c in chain] and o[0].get(metric) is not None \
                and (d_best.get(metric) is None or o[0][metric] > d_best[metric] + 0.05):
            alt[metric] = {"seq": seq, "igr": o[0]["igr"], "run": o[0].get("run"), "feel": o[0].get("feel"),
                           "stp": o[0].get("stp"), "def": o[0].get("def"), "roles": o[4]}
    steps = []
    for e, path, a, b in chain:
        steps.append({"key": e["key"], "name": e["name"], "path": (path or {}).get("label", ""), "cost": e["cost"],
                      "premium": e["premium"], "gates": gates(ev.fast.detail(a), ev.fast.detail(b), a.attrs, b.attrs, ev.g, ev.cfg),
                      **_changes(a, b)})
    used = {s["key"] for s in steps}
    skipped = []
    for e in cands:
        if e["key"] in used:
            continue
        if not plan_paths(e, ev.g, rules):
            skipped.append([e["name"], "gir bare en angreps-PlayStyle, som ikke hjelper en forsvarer"])
            continue
        why = _first_block(e, last, rules)
        skipped.append([e["name"], f"blir stengt: {why}" if why else "gir ingenting for kortet"])
    # where the order matters: evo i must come before the later evos j that would shut it out
    blocks: Dict[int, List[Tuple[str, str]]] = {}
    for i in range(len(chain)):
        for j in range(i + 1, len(chain)):
            ei, ej = chain[i][0], chain[j][0]
            before = chain[i][2]
            if check(ej, before, rules) is not None:
                continue
            why = check(ei, apply(ej, before, rules, chain[j][1]), rules)
            if why and why[0] in ("ovr", "pace", "ps", "psp"):
                blocks.setdefault(i, []).append((ej["name"], why[0]))
    tips = []
    for i, lst in blocks.items():
        later = [n for n, _ in lst]
        names = later[0] if len(later) == 1 else ", ".join(later[:-1]) + " og " + later[-1]
        cat = Counter(c for _, c in lst).most_common(1)[0][0]
        tips.append(f"{chain[i][0]['name']} før {names} (ellers {REASON_WORDS.get(cat, cat)})")
    return {"igr": round(v, 1), "ovr": fin.ovr, "steps": steps, "roles": rpp, "skip": skipped, "tips": tips[:3],
            "proven": bool(complete) and not quick, "quick": bool(quick),
            "near": near[:4], "chk": unchecked, "acc": d_best["acc"], "feel": d_best["feel"], "run": d_best["run"],
            "vil": d_best.get("vil"), "eff": d_best.get("eff"), "pace": d_best.get("pace"), "alt": alt,
            "stp": d_best.get("stp"), "stb": d_best.get("stb"), "stl": d_best.get("stl"), "def": d_best.get("def"),
            "seq": [[c[0]["key"], (c[1] or {}).get("label", "")] for c in chain], "_state": fin}


# ---------------------------------------------------------------- future evos

def _wchoice(rng: random.Random, items: Dict[str, float], k: int) -> List[str]:
    pool = {a: float(w) for a, w in items.items() if not str(a).startswith("_") and w}
    out = []
    for _ in range(min(k, len(pool))):
        tot = sum(pool.values())
        x, acc = rng.random() * tot, 0.0
        for a, w in pool.items():
            acc += w
            if acc >= x:
                out.append(a)
                del pool[a]
                break
    return out


def generate_universe(lab: dict, u: int) -> List[List[dict]]:
    """Evos per future wave for universe u (the same for every card, so cards are compared fairly)."""
    fut = lab["future"]
    rng = random.Random(int(fut.get("seed", 27)) * 1000 + u)
    waves = []
    for wi, w in enumerate(fut["waves"]):
        evos = []
        for g, pinfo in fut["positions"].items():
            pool = fut["pools"].get(g)
            if not pool:
                continue
            for i in range(int(w.get("evos", 3))):
                R = rng.randint(*w["max_ovr"])
                fill = R < w.get("fill_below", 0) and rng.random() < w.get("fill_share", 0)
                cap = R + rng.randint(*w["ovr_cap_add"])
                n = rng.randint(*w["stats"])
                stats = {}
                for a in _wchoice(rng, pool["stats"], n):
                    weight = pool["stats"][a]
                    scap = cap + rng.randint(*w["stat_cap_add"]) - (0 if weight >= 0.6 else rng.randint(2, 6))
                    stats[a] = [40 if fill else rng.randint(*w["stat_boost"]), min(99, scap)]
                positions = list(pinfo["positions"])
                if pinfo.get("sides") and rng.random() < 0.5:
                    positions = list(rng.choice(pinfo["sides"]))
                excl = []
                if pinfo.get("exclude") and rng.random() < w.get("excl_share", 0.5):
                    excl = _wchoice(rng, {x: 1 for x in pinfo["exclude"]}, rng.randint(1, 2))
                req = {"max_ovr": R, "positions": positions, "not_positions": excl,
                       "max_ps": 7 if rng.random() < 0.85 else None}
                if g in ("ST", "W", "CAM", "FB") and rng.random() < w.get("pace_req_share", 0.5):
                    req["max_pace"] = R + rng.randint(*w["pace_req_add"])
                up = {"ovr": [40 if fill else rng.randint(*w["ovr_gain"]), cap], "stats": stats}
                if rng.random() < w.get("ps", 0.7):
                    opts = _wchoice(rng, pool["playstyles"], 2)
                    if rng.random() < w.get("ps_plus", 0.1) and opts:
                        up["paths"] = [{"label": opts[0] + "+", "psp": [opts[0]]}] + [{"label": o, "ps": [o]} for o in opts[1:]]
                    else:
                        up["paths"] = [{"label": o, "ps": [o]} for o in opts]
                if rng.random() < w.get("wf", 0):
                    up["wf"] = [1, 4]
                if rng.random() < w.get("sm", 0):
                    up["sm"] = [1, 4]
                evos.append(parse_evo({"key": f"u{u}w{wi}{g}{i}", "name": f"{w['name']} {g} {i + 1}", "req": req, "up": up,
                                       "source": "sim"}))
            # a PlayStyle evo for cards with few PlayStyles
            opts = _wchoice(rng, pool["playstyles"], 2)
            evos.append(parse_evo({"key": f"u{u}w{wi}{g}ps", "name": f"{w['name']} {g} PlayStyle",
                                   "req": {"max_ovr": rng.randint(*w.get("ps_evo_max_ovr", w["max_ovr"])),
                                           "positions": list(pinfo["positions"]), "max_ps": rng.choice([2, 3])},
                                   "up": {"paths": [{"label": o, "ps": [o]} for o in opts]}, "source": "sim"}))
        evos.sort(key=lambda e: (e["req"]["max_ovr"] or 99, e["req"].get("max_pace") or 99))
        waves.append(evos)
    return waves


def _ps_value(name: str, plus: bool, group: str, cfg: dict) -> float:
    ps = cfg["playstyles"]
    e = ps["playstyles"].get(name)
    if not e:
        return 0.0
    rel = (e.get("relevance") or ps["category_relevance"][e["category"]]).get(group, 0.0)
    return e["plus" if plus else "base"] * rel


def _best_path(evo: dict, st: State, group: str, cfg: dict, allowed: Optional[list] = None) -> Optional[dict]:
    paths = [p for p in (allowed if allowed is not None else evo["up"]["paths"]) if p]
    if not paths:
        return None

    def val(p):
        v = 0.0
        for n, _cap in p.get("ps", []):
            if n not in st.ps and n not in st.psp:
                v += _ps_value(n, False, group, cfg)
        for n, _cap in p.get("psp", []):
            if n not in st.psp:
                v += _ps_value(n, True, group, cfg) - (_ps_value(n, False, group, cfg) if n in st.ps else 0)
        return v
    return max(paths, key=val)


_WAVE_CACHE: Dict[tuple, tuple] = {}


def card_waves(universes: Dict[int, List[List[dict]]], u: int, positions: Tuple[str, ...]) -> List[Tuple[List[dict], int]]:
    """Per wave: the evos of universe u for one of the card's positions that its positions do not
    shut it out of, and how many it is shut out of (cached per position set)."""
    out = []
    for wi, evos in enumerate(universes[u]):
        k = (id(universes), u, wi, positions)
        hit = _WAVE_CACHE.get(k)
        if hit is None:
            ok, shut = [], 0
            for e in evos:
                r = e["req"]
                if r["positions"] and not any(x in r["positions"] for x in positions):
                    continue
                if any(x in r["not_positions"] for x in positions) or (
                        r["max_positions"] is not None and len(positions) > r["max_positions"]):
                    shut += 1
                    continue
                ok.append(e)
            hit = _WAVE_CACHE[k] = (ok, shut)
        out.append(hit)
    return out


def _check_dyn(e: dict, st: State, rules: dict) -> Optional[str]:
    """check() without the position tests (done once per card in card_waves)."""
    r = e["req"]
    if r["requires_evo"] and r["requires_evo"] not in st.done:
        return "pre"
    if r["min_ovr"] is not None and st.ovr < r["min_ovr"]:
        return "ovr"
    if r["max_ovr"] is not None and st.ovr > r["max_ovr"]:
        return "ovr"
    if r["max_pace"] is not None:
        pac = face_value(st.attrs, "pace", rules)
        if pac is not None and pac > r["max_pace"]:
            return "pace"
    if r["max_ps"] is not None and ps_count(st, rules) > r["max_ps"]:
        return "ps"
    if r["max_psp"] is not None and len(st.psp) > r["max_psp"]:
        return "psp"
    return None


def _apply_inplace(e: dict, s: State, rules: dict, path: Optional[dict]) -> None:
    """apply() without copying the state (simulations only)."""
    _apply_core(e, s, rules, path)


def simulate_universe(st0: State, waves: List[Tuple[List[dict], int]], ev: Evaluator, rules: dict,
                      tally: Optional[Counter] = None, rate_each: bool = True) -> Tuple[List[float], List[int], State]:
    """IGR and OVR after each wave when the card takes every evo it qualifies for
    (waves from card_waves, most restrictive evo first)."""
    st = st0.copy()
    igrs, ovrs = [], []
    offered = applied = 0
    why_n: Dict[str, int] = {}
    for evos, shut in waves:
        offered += len(evos) + shut
        if shut:
            why_n["pos"] = why_n.get("pos", 0) + shut
        for e in evos:
            why = _check_dyn(e, st, rules)
            if why:
                why_n[why] = why_n.get(why, 0) + 1
                continue
            allowed = plan_paths(e, ev.g, rules)
            if not allowed:
                continue
            applied += 1
            _apply_inplace(e, st, rules, _best_path(e, st, ev.g, ev.cfg, allowed) if e["up"]["paths"] else allowed[0])
        if rate_each:
            igrs.append(round(ev.igr(st), 2))
        ovrs.append(st.ovr)
    if tally is not None:
        tally["offered"] += offered
        tally["applied"] += applied
        for k, n in why_n.items():
            tally[k] += n
    return igrs, ovrs, st


# ---------------------------------------------------------------- one card

def eligible(p: Player, lab: dict) -> Tuple[bool, str]:
    el = lab["eligible"]
    if p.status == "lekket" and el.get("exclude_leaks", True):
        return False, "lekket kort, ikke utgitt ennå"
    version = (p.rarity or "").lower()
    for word in el.get("excluded_versions", []):
        if word.lower() in version:
            return False, f"{word}-kort er ikke med i vanlige evoer"
    if p.ovr is not None and p.ovr > el.get("max_start_ovr", 86):
        return False, f"for høy OVR for evoer ({p.ovr})"
    if p.position == "GK" and not el.get("include_gk", True):
        return False, "keepere er ikke med"
    return True, ""


def card_group(p: Player) -> Optional[str]:
    return position_group(p.position)


def simulate_card(p: Player, cfg: dict, lab: dict, live: List[dict], universes: Dict[int, List[List[dict]]],
                  want: Sequence[int], prev: Optional[dict] = None, quick: bool = False) -> dict:
    """Cache entry for one card: live plan, IGR per wave in each universe, and the median build.
    quick: the live plan from the fast search only (redone in full next run)."""
    rules = lab["rules"]
    g = card_group(p) or "ST"
    ev = Evaluator(p, g, cfg, rules)
    st0 = state_from(p)
    if prev:
        entry = prev
        live_state = _state_from_entry(st0, entry["live"])
    else:
        now = ev.igr(st0)
        plan = plan_live(p, st0, live, ev, rules, quick=quick)
        live_state = plan.pop("_state")
        entry = {"g": g, "now": now, "ovr": st0.ovr, "live": plan, "mc": {}, "tally": {}, "med": None,
                 "_ld": _state_delta(st0, live_state)}
        entry["live"]["ld"] = entry.pop("_ld")
    tally = Counter(entry.get("tally") or {})
    for u in want:
        if str(u) in entry["mc"]:
            continue
        igrs, ovrs, _ = simulate_universe(live_state, card_waves(universes, u, st0.positions), ev, rules, tally)
        entry["mc"][str(u)] = [igrs, ovrs]
    entry["tally"] = dict(tally)
    # the same futures without today's evos: the page uses it to adjust the forecast when you mark evos as used
    entry.setdefault("mc0", {})
    if entry["live"].get("steps"):
        for u in want:
            if str(u) not in entry["mc0"]:
                igrs0, ovrs0, _ = simulate_universe(st0, card_waves(universes, u, st0.positions), ev, rules)
                entry["mc0"][str(u)] = [igrs0, ovrs0]
    # median build over the universes done so far (final wave), rebuilt from that universe
    us = sorted(entry["mc"], key=lambda k: entry["mc"][k][0][-1])
    mid = us[len(us) // 2]
    if not entry.get("med") or entry["med"].get("u") != mid:
        _, _, fin = simulate_universe(live_state, card_waves(universes, int(mid), st0.positions), ev, rules, rate_each=False)
        d = ev.fast.detail(fin)
        ev.calls += 1
        entry["med"] = {"u": mid, "acc": d["acc"], "feel": d["feel"], "run": d["run"], "vil": d.get("vil"), "eff": d.get("eff"),
                        "pace": d.get("pace"), "stp": d.get("stp"), "stb": d.get("stb"), "stl": d.get("stl"),
                        "igr": d["igr"], **_changes(st0, fin)}
    entry["calls"] = entry.get("calls", 0) + ev.calls
    return entry


def _state_delta(a: State, b: State) -> dict:
    return {"a": {k: v for k, v in b.attrs.items() if abs(v - a.attrs.get(k, v)) > 1e-9}, "o": b.ovr,
            "ps": b.ps, "psp": b.psp, "wf": b.wf, "sm": b.sm, "r": b.roles, "rar": b.rarity, "done": b.done}


def _apply_delta(st0: State, d: dict) -> State:
    s = st0.copy()
    s.attrs.update(d["a"])
    s.ovr, s.ps, s.psp, s.wf, s.sm = d["o"], list(d["ps"]), list(d["psp"]), d["wf"], d["sm"]
    s.roles = {k: dict(v) for k, v in d["r"].items()}
    s.rarity, s.done = d.get("rar", s.rarity), list(d.get("done", []))
    return s


def _state_from_entry(st0: State, live: dict) -> State:
    return _apply_delta(st0, live["ld"])


# ---------------------------------------------------------------- cache and run

def _fingerprint(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:16]


def card_fingerprint(p: Player) -> str:
    return _fingerprint([p.name, p.rarity, p.ovr, p.position, p.alt_positions, p.attributes, p.playstyles, p.playstyles_plus,
                         p.playstyles_complete, p.weak_foot, p.skill_moves, p.roles, p.height_cm, p.gender, p.body_type, p.weight_kg,
                         p.status, p.accelerate_source, p.off_balance_dribbling, p.work_rate_att, p.birthdate, positions_unsure(p)])


def config_fingerprint(cfg: dict, lab: dict, live: List[dict]) -> str:
    sim = {k: v for k, v in lab.items() if k not in ("op", "favorites", "live")}
    # how long a run may take and on how many cores does not change the results
    sim["future"] = {k: v for k, v in (lab.get("future") or {}).items() if k not in ("max_minutes", "workers")}
    return _fingerprint([CACHE_VERSION, sim, live, cfg["weights"], cfg["playstyles"]])


_UNIVERSES: Dict[str, Dict[int, List[List[dict]]]] = {}


def _universes(lab: dict, n_u: int) -> Dict[int, List[List[dict]]]:
    k = _fingerprint([lab["future"], n_u])
    if k not in _UNIVERSES:
        _UNIVERSES[k] = {u: generate_universe(lab, u) for u in range(n_u)}
    return _UNIVERSES[k]


def _simulate_many(jobs: list, cfg: dict, lab: dict, live: List[dict], n_u: int, want: List[int],
                   quick: bool = False) -> Dict[str, dict]:
    universes = _universes(lab, n_u)
    return {p.uid: simulate_card(p, cfg, lab, live, universes, want, prev, quick=quick) for p, prev in jobs}


def _workers(setting) -> int:
    import os
    if isinstance(setting, int):
        return max(1, setting)
    return max(1, min(8, os.cpu_count() or 1))   # the main process only waits, so every core simulates


def _simulate_jobs(jobs: list, cfg: dict, lab: dict, live: List[dict], n_u: int, want: List[int], workers: int,
                   quick: bool = False, deadline: Optional[float] = None, on_part=None) -> Tuple[Dict[str, dict], list]:
    """Run the simulations, split over several processes when there are many cards (one process if that is
    not possible on this machine). With a deadline (time.time()), no new card is started after it: returns
    (entries, the jobs not done). on_part(entries so far) is called every few minutes (to save progress)."""
    import time
    out: Dict[str, dict] = {}
    last = [time.time()]

    def progress():
        if on_part and time.time() - last[0] > 240:
            on_part(out)
            last[0] = time.time()

    def one_process(todo: list) -> list:
        for i, (p, prev) in enumerate(todo):
            if deadline is not None and time.time() >= deadline:
                return todo[i:]
            out.update(_simulate_many([(p, prev)], cfg, lab, live, n_u, want, quick))
            progress()
        return []
    if not jobs:
        return out, []
    if workers <= 1 or len(jobs) < 300:
        return out, one_process(jobs)
    # small chunks, so the deadline is kept and a few slow cards do not hold up one process at the end
    size = max(10, min(60, len(jobs) // (workers * 12) + 1))
    chunks = [jobs[i:i + size] for i in range(0, len(jobs), size)]
    left: list = []
    try:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_simulate_many, ch, cfg, lab, live, n_u, want, quick): ch for ch in chunks}
            stopped = False
            for f in as_completed(futs):
                if f.cancelled():   # not started before the deadline: in left already
                    continue
                out.update(f.result())
                progress()
                if not stopped and deadline is not None and time.time() >= deadline:
                    stopped = True
                    for g, ch in futs.items():
                        if g.cancel():
                            left.extend(ch)
        return out, left
    except Exception as err:  # e.g. no permission to start processes
        print(f"  (kjører Evo Lab i én prosess: {type(err).__name__})")
        todo = [(p, prev) for p, prev in jobs if p.uid not in out]
        return out, one_process(todo)


def _deadline(fut: dict) -> Optional[float]:
    """When Evo Lab stops starting full plan searches (time.time()): future.max_minutes from now, and never
    after FC_FRIST (seconds since 1970, set by the workflow so the whole run stays within its time limit)."""
    import os
    import time
    ends = []
    if fut.get("max_minutes"):
        ends.append(time.time() + 60 * float(fut["max_minutes"]))
    try:
        if os.environ.get("FC_FRIST"):
            ends.append(float(os.environ["FC_FRIST"]))
    except ValueError:
        pass
    return min(ends) if ends else None


def run(players: List[Player], results: List[dict], cfg: dict, lab: Optional[dict] = None,
        cache_path: Optional[Path] = None, today: Optional[date] = None, quiet: bool = False,
        user_file: Optional[Path] = None, used_file: Optional[Path] = None, ignore_used: bool = False) -> dict:
    """Simulate every eligible card. Returns {"entries": {uid: entry}, "live": [...], "expired": [...], ...}.
    ignore_used: plan as if no evo is used up (for a page shared with others; each viewer ticks their own)."""
    import time
    t0 = time.time()
    lab = lab or load_lab_config()
    live, expired = active_live(lab, today, user_file)
    used = set() if ignore_used else set(load_used(used_file))
    used_names = [e["name"] for e in live if e["key"].lower() in used or e["name"].lower() in used]
    live = [e for e in live if e["name"] not in used_names]
    fp_cfg = config_fingerprint(cfg, lab, live)
    cache_path = Path(cache_path) if cache_path else ROOT / "data" / "evolab_cache.pkl"
    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                raw = pickle.load(f)
            if raw.get("cfg") == fp_cfg:
                cache = raw.get("cards", {})
        except Exception:  # an old or broken cache is simply rebuilt
            cache = {}
    fut = lab["future"]
    n_u = int(fut.get("universes", 12))
    stage1 = list(range(min(2, n_u)))
    workers = _workers(fut.get("workers", "auto"))
    cands = []
    skipped: Dict[str, str] = {}
    for p in players:
        ok, why = eligible(p, lab)
        if ok and card_group(p):
            cands.append(p)
        else:
            skipped[p.uid] = why or "ukjent posisjon"
    entries: Dict[str, dict] = {}
    fps: Dict[str, str] = {}
    jobs = []
    for p in cands:
        fp = card_fingerprint(p)
        fps[p.uid] = fp
        prev = cache.get(fp)
        if prev and all(str(u) in prev["mc"] for u in stage1):
            entries[p.uid] = prev   # a plan from the fast search only is done in full below, when there is time
            continue
        jobs.append((p, prev if prev and not prev["live"].get("quick") else None))
    deadline = _deadline(fut)

    def save(extra: Optional[Dict[str, dict]] = None) -> None:
        cards = {fps[uid]: e for uid, e in entries.items()}
        for uid, e in (extra or {}).items():
            cards[fps[uid]] = e
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                pickle.dump({"cfg": fp_cfg, "saved": date.today().isoformat(), "cards": cards}, f,
                            protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(cache_path)
        except OSError:
            pass
    # 1) every new or changed card gets a plan from the fast search first (a fraction of the time of the full
    #    search), so every card has a plan whatever happens later in the run
    if jobs:
        if len(jobs) > 500 and not quiet:
            print(f"Evo Lab: raskt plansøk for {len(jobs)} kort med {workers} prosess{'er' if workers > 1 else ''} ...", flush=True)
        entries.update(_simulate_jobs(jobs, cfg, lab, live, n_u, stage1, workers, quick=True, on_part=save)[0])
        save()
    new = len(jobs)
    # 2) the full search (every way to use the evos), the cards that end highest in their position first, until the
    #    deadline. The rest keep the fast plan this run and are done first in the next.
    by_group: Dict[str, List[float]] = {}
    for p in cands:
        by_group.setdefault(entries[p.uid]["g"], []).append(entries[p.uid]["live"]["igr"])
    for v in by_group.values():
        v.sort()

    def share_above(p: Player) -> float:
        v = by_group[entries[p.uid]["g"]]
        return (len(v) - bisect.bisect_right(v, entries[p.uid]["live"]["igr"])) / len(v)
    todo = sorted((p for p in cands if entries[p.uid]["live"].get("quick")), key=share_above)
    if len(todo) > 500 and not quiet:
        print(f"Evo Lab: fullt plansøk for {len(todo)} kort, de som ender høyest først"
              + (f" (til kl. {datetime.fromtimestamp(deadline).strftime('%H:%M')})" if deadline else "") + " ...", flush=True)
    done, left = _simulate_jobs([(p, None) for p in todo], cfg, lab, live, n_u, stage1, workers, deadline=deadline,
                                on_part=save)
    entries.update(done)
    quick = len(left)
    save()
    # stage 2: every future for the best cards per position and OVR
    per = int(fut.get("stage2_per_bucket", 15))
    buckets: Dict[Tuple[str, int], List[Tuple[float, Player]]] = {}
    for p in cands:
        e = entries[p.uid]
        finals = [e["mc"][str(u)][0][-1] for u in stage1 if str(u) in e["mc"]]  # stage-1 futures only, so the choice is stable
        buckets.setdefault((e["g"], int(p.ovr or 0)), []).append((statistics.median(finals), p))
    full = set()
    for lst in buckets.values():
        lst.sort(key=lambda t: t[0], reverse=True)
        full.update(p.uid for _, p in lst[:per])
    by_uid = {p.uid: p for p in cands}
    jobs = [(by_uid[uid], entries[uid]) for uid in sorted(full, key=lambda u: share_above(by_uid[u]))
            if not all(str(u) in entries[uid]["mc"] for u in range(n_u))]
    # after the deadline the rest keep the quick estimate from two futures (marked «grovt anslag»)
    done2, left2 = _simulate_jobs(jobs, cfg, lab, live, n_u, list(range(n_u)), workers, deadline=deadline, on_part=save)
    entries.update(done2)
    more = len(done2)
    save()
    if not quiet:
        print(f"Evo Lab: {len(cands)} kort ({new} nye eller endret, {len(done)} med fullt plansøk nå, {more} med alle {n_u} "
              f"fremtider) på {time.time() - t0:.0f} s"
              + (f". {quick} kort har bare planen fra det raske søket (tidsgrensen), de tas neste kjøring" if quick else "")
              + (f". {len(left2)} kort rakk ikke alle fremtidene" if left2 else ""))
        if expired:
            print(f"  {len(expired)} live-evoer har gått ut ({', '.join(expired[:4])}{' ...' if len(expired) > 4 else ''}). "
                  f"Legg inn nye med: py -m fcrating evo-import")
    return {"entries": entries, "live": live, "expired": expired, "used": used_names, "skipped": skipped, "universes": n_u,
            "full": full, "lab": lab, "quick": quick}


# ---------------------------------------------------------------- summary per card

def _q(vals: List[float], q: float) -> float:
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    x = q * (len(s) - 1)
    lo = int(x)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (x - lo)


def _top_threshold(vals_sorted_desc: List[float], pct: float) -> float:
    k = max(1, int(round(len(vals_sorted_desc) * pct / 100.0)))
    return vals_sorted_desc[min(k, len(vals_sorted_desc)) - 1]


def dna(r: dict, cfg: dict) -> dict:
    """What evolutions cannot change, as IGR points (and the AcceleRATE the card can reach)."""
    w = cfg["weights"]
    g = r.get("position_group") or r.get("best_group")
    out = {"pts": 0.0, "chips": [], "acc_cap": None}
    if g == "GK":
        gk = r["by_group"].get("GK", {}).get("gk_height", 0.0)
        out["pts"] = round(gk, 2)
        if r.get("height_cm"):
            out["chips"].append([f"{round(r['height_cm'])} cm", round(gk, 1)])
        return out
    bl = w["blend"].get(g, {})
    fp = r.get("feel_parts") or {}
    bf, br = bl.get("feel", 0.0), bl.get("run", 0.0)
    h_pts = (fp.get("height") or 0.0) * bf
    b_pts = (fp.get("body_type") or 0.0) * bf
    rc = w.get("run_ai") or {}
    run_pts = 0.0
    if br and rc and r.get("height_cm"):
        from .runs import short_body_value
        sw = _clean(rc["weights"])
        share = sw.get("kort_kropp", 0) / (sum(v for v in sw.values() if v) or 1)
        sb = _clean(rc["short_body"])
        run_pts = (short_body_value(r["height_cm"], rc) - sb["ref_value"]) * share * br
    attrs = r.get("attributes") or {}
    rules = w["accelerate_rules"]
    feel_acc = w["feel"]["accelerate"]
    pace_acc = w["pace"]["accelerate"]
    best_type, best_pts = r.get("accelerate"), None
    tries = [dict(attrs, agility=max(attrs.get("agility", 0), 92), acceleration=max(attrs.get("acceleration", 0), 92)),
             dict(attrs, strength=max(attrs.get("strength", 0), 92), acceleration=max(attrs.get("acceleration", 0), 85)),
             dict(attrs)]
    for a in tries:
        t, _ = acc_mod.classify(a, r.get("height_cm"), r.get("gender") or "M", rules)
        if not t:
            continue
        pts = feel_acc.get(t, 0.0) * bf + pace_acc.get(t, 0.0) * bl.get("pace", 0.0)
        if best_pts is None or pts > best_pts:
            best_type, best_pts = t, pts
    out["acc_cap"] = best_type
    out["pts"] = round(h_pts + b_pts + run_pts + (best_pts or 0.0), 2)
    if r.get("height_cm"):
        out["chips"].append([f"{round(r['height_cm'])} cm", round(h_pts + run_pts, 1)])
    if fp.get("body_type"):
        out["chips"].append(["Kroppstype", round(b_pts, 1)])
    if best_type and best_type != r.get("accelerate"):
        out["chips"].append([f"Kan bli {best_type}", round((best_pts or 0.0) - (feel_acc.get(r.get('accelerate') or '', 0.0) * bf
                                                                               + pace_acc.get(r.get('accelerate') or '', 0.0) * bl.get('pace', 0.0)), 1)])
    elif best_type:
        out["chips"].append([f"{best_type} (tak)", None])
    if r.get("skill_moves") == 5:
        out["chips"].append(["Skill moves 5★", None])
    if r.get("weak_foot") == 5:
        out["chips"].append(["Svakfot 5★", None])
    return out


def summarize(lab_run: dict, players: List[Player], results: List[dict], cfg: dict) -> Dict[str, dict]:
    """Per card: P10/P50/P90 per horizon (comparable to today's IGR), OP chance, when it gets OP,
    which card today it would match, locked DNA, evo access and likeness to your favourites."""
    lab = lab_run["lab"]
    hz = horizons(lab)
    op = lab.get("op", {})
    top_pct = float(op.get("top_pct", 5))
    drift = op.get("meta_drift", {})
    by_uid = {r["uid"]: r for r in results}
    pools: Dict[str, List[Tuple[float, dict]]] = {}
    for r in results:
        for g, gr in r["by_group"].items():
            pools.setdefault(g, []).append((gr["igr"], r))
    asc: Dict[str, List[float]] = {}
    thr: Dict[str, float] = {}
    for g in pools:
        pools[g].sort(key=lambda t: t[0])
        asc[g] = [v for v, _ in pools[g]]
        thr[g] = _top_threshold(asc[g][::-1], top_pct)
    favs = _favorites(lab, results)
    from .profile import categories, order as prof_order
    has_prof = "profile" in cfg["weights"]
    cat_keys = prof_order(cfg) if has_prof else []
    players_by = {p.uid: p for p in players}

    def cat_vals(base_r: dict, g: str, attrs: Dict[str, float], d: dict) -> Optional[list]:
        """Every profile category of an evolved build (attribute scale)."""
        if not has_prof or g == "GK":
            return None
        pseudo = {"position": base_r.get("position"), "feel": d.get("feel"), "attributes": attrs,
                  "run_ai": {"score": d.get("run"), "decision": d.get("vil"), "execution": d.get("eff")} if base_r.get("run_ai") else None,
                  "hard_to_stop": {"score": d.get("stp")} if d.get("stp") is not None else None}
        cats = categories(pseudo, cfg)
        return [None if cats.get(k) is None else round(cats[k], 1) for k in cat_keys]
    from .runs import distance, run_cfg, similarity_pct, similarity_stats
    rc = run_cfg(cfg) if "run_ai" in cfg["weights"] else None
    sim_stats = similarity_stats(results, rc) if rc and favs else {}
    out: Dict[str, dict] = {}
    dna_vals: Dict[str, List[float]] = {}
    for uid, e in lab_run["entries"].items():
        r = by_uid.get(uid)
        if not r:
            continue
        g = e["g"]
        if g not in r["by_group"]:
            continue
        ranked_now = r["by_group"][g]["igr"]
        off = ranked_now - e["now"]
        n_done = len(e["mc"])
        coarse = n_done < lab_run["universes"]
        hs = []
        when = None
        for hi, h in enumerate(hz):
            if h["key"] == "live":
                vals = [e["live"]["igr"] + off]
                ovrs = [e["live"]["ovr"]]
            else:
                vals = [v[0][hi - 1] + off for v in e["mc"].values()]
                ovrs = [v[1][hi - 1] for v in e["mc"].values()]
            t = thr.get(g, 99) + float(drift.get(h["key"], 0.0))
            p50 = _q(vals, 0.5)
            better = len(asc[g]) - bisect.bisect_right(asc[g], p50)
            hs.append({"p10": round(_q(vals, 0.1), 1), "p50": round(p50, 1), "p90": round(_q(vals, 0.9), 1),
                       "op": round(100.0 * sum(1 for v in vals if v >= t) / len(vals)), "thr": round(t, 1),
                       "ovr": int(round(statistics.median(ovrs))), "rank": better + 1, "of": len(asc[g])})
            # the same horizon if the card took none of today's evos (for the page's used-evo filter)
            mc0 = [e["mc0"][u] for u in e["mc"] if u in (e.get("mc0") or {})]
            if h["key"] != "live" and mc0 and len(mc0) == len(e["mc"]):
                v0 = [v[0][hi - 1] + off for v in mc0]
                hs[-1]["z"] = [round(_q(v0, 0.1), 1), round(_q(v0, 0.5), 1), round(_q(v0, 0.9), 1),
                               round(100.0 * sum(1 for v in v0 if v >= t) / len(v0)),
                               int(round(statistics.median(v[1][hi - 1] for v in mc0)))]
            if when is None and p50 >= t:
                when = hi
        final = hs[-1]["p50"]
        i = bisect.bisect_left(asc[g], final)
        near = min((j for j in (i - 1, i) if 0 <= j < len(asc[g])), key=lambda j: abs(asc[g][j] - final), default=None)
        like = pools[g][near][1] if near is not None else None
        # evo access among the future evos whose OVR limit the card met: what else shuts it out?
        tally = e.get("tally") or {}
        offered = tally.get("offered", 0) - tally.get("ovr", 0)
        blockers = sorted(((k, tally.get(k, 0)) for k in ("pace", "ps", "pos", "psp")), key=lambda t: t[1], reverse=True)
        dn = dna(r, cfg)
        dna_vals.setdefault(g, []).append(dn["pts"])
        fav, fav_live = [], []
        if favs and rc and g != "GK":
            def likeness(changed: Dict[str, float]) -> list:
                pseudo = {"attributes": dict(r["attributes"], **changed), "height_cm": r.get("height_cm"),
                          "work_rate_att": r.get("work_rate_att")}
                out_l = []
                for f in favs:
                    if f["uid"] == uid:
                        continue  # the favourite itself
                    d = distance(pseudo, f, sim_stats, rc)
                    if d is not None:
                        out_l.append([f["name"], similarity_pct(d)])
                return out_l
            if e.get("med"):   # after a typical year
                fav = likeness({k: a for k, b, a in e["med"]["d"]})
            fav_live = likeness(dict(e["live"]["ld"]["a"]))   # with the plan for the evos out now
        # profile categories now, after the live plan and after a typical year (top % in the position)
        cats = {"now": None, "live": None, "end": None}
        if has_prof and g != "GK":
            pr = r.get("profile") or {}
            cats["now"] = [None if (pr.get("cats") or {}).get(k) is None else round(pr["cats"][k], 1) for k in cat_keys]
            pl = players_by.get(uid)
            if pl is not None:
                st0 = state_from(pl)
                lv_attrs = dict(st0.attrs)
                lv_attrs.update(e["live"]["ld"]["a"])
                cats["live"] = cat_vals(r, g, lv_attrs, e["live"])
                if e.get("med"):
                    end_attrs = dict(st0.attrs)
                    for k, b0, a0 in e["med"]["d"]:
                        end_attrs[k] = a0
                    cats["end"] = cat_vals(r, g, end_attrs, e["med"])
        ra = r.get("run_ai") or {}
        hs0 = r.get("hard_to_stop") or {}
        md = e.get("med") or {}
        out[uid] = {
            "cats": cats, "runcard": bool(ra),
            "stops": {"now": [hs0.get("score"), hs0.get("ball"), hs0.get("run")],
                      "live": [e["live"].get("stp"), e["live"].get("stb"), e["live"].get("stl")],
                      "end": [md.get("stp"), md.get("stb"), md.get("stl")]} if hs0 else None,
            "runs": {"now": [ra.get("score"), ra.get("decision"), ra.get("execution")],
                     "live": [e["live"].get("run"), e["live"].get("vil"), e["live"].get("eff")],
                     "end": [(e.get("med") or {}).get("run"), (e.get("med") or {}).get("vil"), (e.get("med") or {}).get("eff")]},
            "g": g, "ovr": r.get("ovr"), "now": round(ranked_now, 1), "rank_now": r["by_group"][g].get("rank"), "h": hs, "when": when,
            "gain": round(final - ranked_now, 1), "coarse": coarse,
            "like": [like["name"], like.get("rarity") or ""] if like and like is not r else None,
            "access": round(100.0 * tally.get("applied", 0) / offered) if offered > 0 else None,
            "block": [[k, round(100.0 * n / offered)] for k, n in blockers if n and offered > 0][:2],
            "dna": dn, "fav": fav, "fav_live": fav_live, "live": e["live"], "med": e.get("med"),
            "ps_est": bool(r["by_group"][g].get("ps_estimated")),
        }
    for g in dna_vals:
        dna_vals[g].sort()
    for uid, s in out.items():
        vals = dna_vals[s["g"]]
        better = len(vals) - bisect.bisect_right(vals, s["dna"]["pts"])
        s["dna"]["top"] = round(100.0 * (better + 1) / len(vals), 1)
    return out


def _favorites(lab: dict, results: List[dict]) -> List[dict]:
    out = []
    for c in (lab.get("favorites") or {}).get("cards", []):
        name, ver = c.get("name", "").lower(), (c.get("version") or "").lower()
        hits = [r for r in results if name and name in r["name"].lower() and r.get("run_ai")]
        if ver:
            hits = [r for r in hits if ver in (r.get("rarity") or "").lower()] or hits
        if hits:
            out.append(max(hits, key=lambda r: r.get("ovr") or 0))
    return out


def update_evos(evos: Dict[str, dict], summary: Dict[str, dict], lab: dict) -> None:
    """Let the main report's "Etter evo" use Evo Lab's result with the evos that are out now
    (real evos, not the forecast for the rest of the year)."""
    for uid, s in summary.items():
        e = evos.get(uid)
        if not e:
            continue
        h = s["h"][0]
        e.update(eligible=True, reason="kan evolueres", igr_now=s["now"], igr_after=h["p50"], evo_value=h["p50"],
                 gain=round(h["p50"] - s["now"], 1), ovr_after=h["ovr"], rank_after=h["rank"], of=h["of"],
                 rank_now=s["rank_now"], accelerate_after=(s.get("live") or {}).get("acc"), boost=None, lab=True)


def attr_label(k: str) -> str:
    return ATTRIBUTE_LABELS.get(k, k)
