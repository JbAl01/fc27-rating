"""Kroppsprofil: points in IGR for the card's body type (build and size) and how it amplifies
Agility, Balance and Dribbling. Config: weights.json "body_profile".

The body type is the same for every card of a player (promo and evo cards inherit it) and no
evolution changes it, so everything except the agility amplification is fixed per card and
position. The agility part uses the attributes after chemistry and evolutions, so Evo Lab shows
what an evo really gives a card with a good body.

FUT.GG shows the nine standard bodies as "Lean Medium", "Average Short" ... (bodytypeCode 1-9)
and a unique (scanned) body as the player's name ("Kylian Mbappé", code 10 or more).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

BUILDS = ("lean", "average", "stocky")
SIZES = ("short", "medium", "tall")
# bodytypeCode (EA): 1 Lean Medium, 2 Average Medium, 3 Stocky Medium, 4 Lean Tall, 5 Average Tall,
# 6 Stocky Tall, 7 Lean Short, 8 Average Short, 9 Stocky Short, 10 and up: unique models
CODES = {1: ("lean", "medium"), 2: ("average", "medium"), 3: ("stocky", "medium"), 4: ("lean", "tall"),
         5: ("average", "tall"), 6: ("stocky", "tall"), 7: ("lean", "short"), 8: ("average", "short"),
         9: ("stocky", "short")}
LABEL_NO = {"lean": "Lean", "average": "Average", "stocky": "Stocky", "short": "Short", "medium": "Medium", "tall": "Tall"}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if not str(k).startswith("_")}


def parse_label(label: Optional[str]) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """(build, size) of a standard body type label in the forms FUT.GG, FUTBIN and SoFIFA use
    ("Lean Medium", "Average Short", "Short & Normal", "Avg & Lean", "Tall & Stocky", "Lean (185+)").
    (None, None) = a unique model (a player's name, 'Unique', 'Messi' ...). None = no label."""
    if not label or not str(label).strip():
        return None
    words = re.findall(r"[a-z]+|\d+\+?", str(label).lower())
    build = next((b for w, b in (("lean", "lean"), ("stocky", "stocky"), ("normal", "average")) if w in words), None)
    size = next((s for w, s in (("short", "short"), ("tall", "tall"), ("medium", "medium")) if w in words), None)
    if build is None and size is not None and ("average" in words or "avg" in words):
        build = "average"
    if build is not None and size is None:
        if "average" in words or "avg" in words or "medium" in words:
            size = "medium"
        elif "185+" in words:
            size = "tall"
        elif "170" in words and "185" in words:
            size = "medium"
    if build in BUILDS and size in SIZES:
        return build, size
    return None, None


def derive(height: Optional[float], weight: Optional[float], gender: Optional[str], dcfg: dict
           ) -> Tuple[Optional[str], Optional[str]]:
    """Size from height, build from BMI (unique models and cards without a body type)."""
    size = build = None
    if height:
        h = height + (dcfg["female_offset_cm"] if gender == "F" else 0)
        size = "short" if h < dcfg["short_below_cm"] else "tall" if h > dcfg["tall_above_cm"] else "medium"
        if weight:
            bmi = weight / (height / 100.0) ** 2
            build = "lean" if bmi < dcfg["lean_below_bmi"] else "stocky" if bmi >= dcfg["stocky_from_bmi"] else "average"
    return build, size


def frame_of(player, bcfg: dict) -> Optional[dict]:
    """The card's body: {"build", "size", "unique", "estimated", "label"} or None if nothing is known."""
    dcfg = bcfg["derive"]
    parsed = parse_label(getattr(player, "body_type", None))
    if parsed is not None and parsed[0] is not None:
        b, s = parsed
        return {"build": b, "size": s, "unique": False, "estimated": False, "label": f"{LABEL_NO[b]} {LABEL_NO[s]}"}
    b, s = derive(player.height_cm, getattr(player, "weight_kg", None), player.gender, dcfg)
    if parsed is not None:   # unique model
        name = str(player.body_type).strip()
        return {"build": b or "average", "size": s or "medium", "unique": True, "estimated": b is None or s is None,
                "label": "Unik" + ("" if name.lower() == "unique" else f" ({name})")}
    if b is None or s is None:
        return None
    return {"build": b, "size": s, "unique": False, "estimated": True, "label": f"{LABEL_NO[b]} {LABEL_NO[s]} (anslått)"}


def frame_code(fr: Optional[dict]):
    """[build 0 lean / 1 average / 2 stocky, size 0 short / 1 medium / 2 tall, unique 0/1, estimated 0/1] or 0:
    what the pages filter on and what 'Ligner på' compares (runs._sim_value)."""
    if not fr:
        return 0
    return [BUILDS.index(fr["build"]), SIZES.index(fr["size"]), 1 if fr["unique"] else 0, 1 if fr["estimated"] else 0]


def _norm(s) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower().strip()


def attach_rep_frames(bcfg: Optional[dict], players) -> None:
    """The bodies with a reputation (standard body types only, read from FUT.GG, not estimated), with height and
    weight, so other cards with the same body type and about the same height and weight share part of it
    (body_profile.reputation.spread). A unique model belongs to one player and is not shared."""
    if not bcfg:
        return
    out = []
    for p in players:
        pts = reputation(p, bcfg)
        fr = frame_of(p, bcfg) if pts else None
        if not fr or fr["unique"] or fr["estimated"] or not p.height_cm:
            continue
        k = f"{fr['build']}_{fr['size']}"
        if not any(x[0] == _norm(p.name) and x[1] == k for x in out):
            out.append([_norm(p.name), k, float(p.height_cm), float(p.weight_kg) if p.weight_kg else None, p.gender or "M", pts])
    bcfg["rep_frames"] = out


def reputation(player, bcfg: dict) -> float:
    """Points for a body with a known feel (body_profile.reputation), on the winger scale."""
    rc = bcfg.get("reputation") or {}
    name, nation = _norm(getattr(player, "name", "")), _norm(getattr(player, "nation", ""))
    rarity = _norm(getattr(player, "rarity", ""))
    # the owner's own list first; the community list (weaker evidence) only for players the owner has not judged
    for part in ("points", "community"):
        for key, v in (rc.get(part) or {}).items():
            if key.startswith("_"):
                continue
            n, _, extra = key.partition("|")   # 'Name', or 'Name|Nation' / 'Name|version' when the name is shared
            if _norm(n) == name and (not extra or _norm(extra) == nation or _norm(extra) in rarity):
                return float(v)
    return 0.0


def is_lean(player, bcfg: Optional[dict]) -> bool:
    """A Lean body (from the body type, or for unique models and cards without one, from height and weight)."""
    if not bcfg:
        return False
    fr = frame_of(player, bcfg)
    return bool(fr and fr["build"] == "lean")


class BodyCard:
    """Everything fixed for one card in one position group; points(attrs, ps, psp) adds the rest.
    model.rate and evolab.FastRater both use this, and the Evo Lab page gets the same numbers
    (const, amp, combos) so the browser computes the same points."""

    def __init__(self, player, group: str, bcfg: Optional[dict]):
        self.on = False
        self.frame = None
        if not bcfg:
            return
        fr = frame_of(player, bcfg)
        self.frame = fr
        if fr is None or group not in bcfg["limits"]:
            return
        amp_cfg = bcfg["agility_amp"]
        f = bcfg["derive"]["estimated_factor"] if fr["estimated"] else 1.0
        b, s = fr["build"], fr["size"]
        const = _clean(bcfg["frame_points"])[group][b][s]
        amp = amp_cfg["frame"][b][s]
        if fr["unique"]:
            u = bcfg["unique"]
            amp = min(u["max_amp"], amp + u["amp_bonus"])
            const += u["points"].get(group, 0.0)
        from .selfcal import learned_points, frame_key
        learn = learned_points(bcfg, group, fr)   # what the players' choices add or take away (selvkalibrering, 50/50)
        self.key = frame_key(fr)
        self.learn = learn * f
        # the body amplifies: positive base points come in full only on an agile card (flex), negative ones always
        fx = bcfg.get("flex") or {}
        share = fx.get("share", 1.0) if const > 0 else 1.0
        self.flex = const * (1.0 - share) * f
        self.fx = (fx.get("floor", 65), fx.get("span", 25), fx.get("cap", 1.2))
        gf = (bcfg.get("combos") or {}).get("group_factor", {}).get(group, 0.0)
        own = reputation(player, bcfg)
        self.rep = own * gf   # known bodies: points whatever the numbers say
        # a card with the same standard body type and about the same height and weight as a known body shares part
        # of its reputation: a good one more the more agile the card is, a bad one always
        self.spread, neg = 0.0, 0.0
        if not own and not fr["unique"] and not fr["estimated"] and player.height_cm:
            sp = (bcfg.get("reputation") or {}).get("spread") or {}
            key, best = f"{b}_{s}", 0.0
            for name, k, h0, w0, g0, pts in bcfg.get("rep_frames") or []:
                if k != key or g0 != (player.gender or "M") or name == _norm(player.name):
                    continue
                sim = max(0.0, 1.0 - abs(player.height_cm - h0) / sp.get("height_cm", 4.0))
                if w0 and getattr(player, "weight_kg", None):
                    sim *= max(0.0, 1.0 - abs(player.weight_kg - w0) / sp.get("weight_kg", 6.0))
                else:
                    sim *= sp.get("no_weight", 0.5)
                v = sp.get("share", 0.5) * pts * sim
                if abs(v) > abs(best):
                    best = v
            if best > 0:
                self.spread = best * gf
            else:
                neg = best * gf
        self.rep += neg
        self.const = (const * share + learn) * f + self.rep
        self.amp = amp * amp_cfg["scale"].get(group, 0.0) * f
        self.syn_w = _clean(amp_cfg["attributes"])
        self.floor, self.span, self.cap = amp_cfg["floor"], amp_cfg["span"], amp_cfg["cap"]
        key = "unique" if fr["unique"] else f"{b}_{s}"
        cc = bcfg.get("combos") or {}
        gf = cc.get("group_factor", {})
        self.combos: List[list] = []
        for c in cc.get("list", []):
            if key not in c["frames"]:
                continue
            fac = (c.get("groups") or gf).get(group, 0.0) * f
            if fac:
                self.combos.append([c["ps"], round(c["points"][0] * fac, 3), round(c["points"][1] * fac, 3)])
        self.combo_cap = cc.get("cap", 1.5)
        self.lo, self.hi = bcfg["limits"][group]
        self.on = True

    def agility(self, attrs: Dict[str, float]) -> Optional[float]:
        """0 .. cap: how agile the card is on the body's scale (weighted average of the attributes)."""
        present = [(attrs[k], v) for k, v in self.syn_w.items() if attrs.get(k) is not None]
        got = sum(v for _, v in present)
        if got <= 0:
            return None
        avg = sum(x * v for x, v in present) / got
        return max(0.0, min(self.cap, (avg - self.floor) / self.span))

    def flexing(self, attrs: Dict[str, float]) -> float:
        """0 .. cap: how much of the body's flexible base points the card earns (agility on a wider scale)."""
        present = [(attrs[k], v) for k, v in self.syn_w.items() if attrs.get(k) is not None]
        got = sum(v for _, v in present)
        if got <= 0 or not (self.flex or self.spread):
            return 0.0
        avg = sum(x * v for x, v in present) / got
        fl, sp, cap = self.fx
        return max(0.0, min(cap, (avg - fl) / sp))

    def combo(self, ps, psp) -> float:
        t = 0.0
        for name, base, plus in self.combos:
            if name in psp:
                t += plus
            elif name in ps:
                t += base
        return min(t, self.combo_cap)

    def points(self, attrs: Dict[str, float], ps, psp) -> float:
        if not self.on:
            return 0.0
        a = self.agility(attrs)
        fx = self.flexing(attrs)
        pts = self.const + self.flex * fx + self.spread * fx + (self.amp * a if a is not None else 0.0) + self.combo(ps, psp)
        return max(self.lo, min(self.hi, pts))

    def upper(self, attrs: Dict[str, float]) -> float:
        """The most the body can give with these attributes (all combos counted at PlayStyle+)."""
        if not self.on:
            return 0.0
        a = self.agility(attrs)
        best = min(self.combo_cap, sum(c[2] for c in self.combos))
        # a body that dampens agility (negative amp) gives the most with the least agility
        fx = self.flexing(attrs)
        return max(self.lo, min(self.hi, self.const + self.flex * fx + self.spread * fx
                                + max(0.0, self.amp * a if a is not None else 0.0) + best))

    def detail(self, attrs: Dict[str, float], ps, psp) -> Optional[dict]:
        if not self.on:
            return None
        a = self.agility(attrs)
        return {"label": self.frame["label"], "unique": self.frame["unique"], "estimated": self.frame["estimated"],
                "key": self.key, "learn": round(self.learn, 2), "rep": round(self.rep + self.spread * self.flexing(attrs), 2),
                "frame": round(self.const + (self.flex + self.spread) * self.flexing(attrs), 2), "amp": round(self.amp * a, 2) if a is not None else 0.0,
                "agility": round(a, 2) if a is not None else None, "combo": round(self.combo(ps, psp), 2),
                "points": round(self.points(attrs, ps, psp), 2)}
