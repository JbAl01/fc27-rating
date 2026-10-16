"""Normalized player schema and name normalization.

Every data source (EA database, CSV export, pasted page text) is converted
into the same Player record, so the rating model never cares where the data
came from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

# Canonical attribute keys (FC 27 in-game attributes).
OUTFIELD_ATTRIBUTES = [
    "acceleration", "sprint_speed",
    "positioning", "finishing", "shot_power", "long_shots", "volleys", "penalties",
    "vision", "crossing", "fk_accuracy", "short_passing", "long_passing", "curve",
    "agility", "balance", "reactions", "ball_control", "dribbling", "composure",
    "interceptions", "heading_accuracy", "def_awareness", "standing_tackle", "sliding_tackle",
    "jumping", "stamina", "strength", "aggression",
]
GK_ATTRIBUTES = ["gk_diving", "gk_handling", "gk_kicking", "gk_reflexes", "gk_positioning", "gk_speed"]
ALL_ATTRIBUTES = OUTFIELD_ATTRIBUTES + GK_ATTRIBUTES


ATTRIBUTE_LABELS = {
    "acceleration": "Acceleration", "sprint_speed": "Sprint Speed", "positioning": "Att. Position",
    "finishing": "Finishing", "shot_power": "Shot Power", "long_shots": "Long Shots", "volleys": "Volleys",
    "penalties": "Penalties", "vision": "Vision", "crossing": "Crossing", "fk_accuracy": "FK Accuracy",
    "short_passing": "Short Passing", "long_passing": "Long Passing", "curve": "Curve", "agility": "Agility",
    "balance": "Balance", "reactions": "Reactions", "ball_control": "Ball Control", "dribbling": "Dribbling",
    "composure": "Composure", "interceptions": "Interceptions", "heading_accuracy": "Heading Accuracy",
    "def_awareness": "Def. Awareness", "standing_tackle": "Standing Tackle", "sliding_tackle": "Sliding Tackle",
    "jumping": "Jumping", "stamina": "Stamina", "strength": "Strength", "aggression": "Aggression",
    "gk_diving": "GK Diving", "gk_handling": "GK Handling", "gk_kicking": "GK Kicking",
    "gk_reflexes": "GK Reflexes", "gk_positioning": "GK Positioning", "gk_speed": "GK Speed",
}


def norm_key(text: str) -> str:
    """'Def. Aware.' -> 'defaware', 'sprintSpeed' -> 'sprintspeed'."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


_ATTRIBUTE_ALIASES = {
    "acceleration": ["acceleration", "acc", "accel"],
    "sprint_speed": ["sprintspeed", "sprint", "ss"],
    "positioning": ["positioning", "attposition", "attpos", "attackingposition", "attackpositioning", "attpositioning",
                    "attackpos", "attackposition"],
    "finishing": ["finishing", "fin"],
    "shot_power": ["shotpower", "shotpow"],
    "long_shots": ["longshots", "longshot"],
    "volleys": ["volleys", "volley"],
    "penalties": ["penalties", "penalty", "pen"],
    "vision": ["vision", "vis"],
    "crossing": ["crossing", "cross"],
    "fk_accuracy": ["fkaccuracy", "fkacc", "freekickaccuracy", "freekick", "fka", "fkaccuracy"],
    "short_passing": ["shortpassing", "shortpass"],
    "long_passing": ["longpassing", "longpass"],
    "curve": ["curve"],
    "agility": ["agility", "agi"],
    "balance": ["balance", "bal"],
    "reactions": ["reactions", "reaction", "rea"],
    "ball_control": ["ballcontrol", "bc"],
    "dribbling": ["dribbling"],
    "composure": ["composure", "com"],
    "interceptions": ["interceptions", "interception", "int"],
    "heading_accuracy": ["headingaccuracy", "headingacc", "heading"],
    "def_awareness": ["defawareness", "defensiveawareness", "defaware", "defawr", "marking"],
    "standing_tackle": ["standingtackle", "standtackle"],
    "sliding_tackle": ["slidingtackle", "slidetackle"],
    "jumping": ["jumping", "jump"],
    "stamina": ["stamina", "sta"],
    "strength": ["strength", "str"],
    "aggression": ["aggression", "agg"],
    "gk_diving": ["gkdiving", "diving"],
    "gk_handling": ["gkhandling", "handling"],
    "gk_kicking": ["gkkicking", "kicking"],
    "gk_reflexes": ["gkreflexes", "reflexes"],
    "gk_positioning": ["gkpositioning"],
    "gk_speed": ["gkspeed"],
}
ATTRIBUTE_ALIASES: Dict[str, str] = {}
for _canon, _names in _ATTRIBUTE_ALIASES.items():
    for _n in _names:
        ATTRIBUTE_ALIASES[_n] = _canon
    ATTRIBUTE_ALIASES[norm_key(_canon)] = _canon


def canonical_attribute(name: str) -> Optional[str]:
    return ATTRIBUTE_ALIASES.get(norm_key(name))


PLAYSTYLES = [
    # Scoring
    "Finesse Shot", "Low Driven Shot", "Power Shot", "Chip Shot", "Gamechanger",
    "Precision Header", "Acrobatic", "Dead Ball",
    # Passing
    "Pinged Pass", "Incisive Pass", "Tiki Taka", "Long Ball Pass", "Whipped Pass", "Inventive",
    # Ball control
    "Technical", "Rapid", "First Touch", "Trickster", "Press Proven",
    # Defending
    "Intercept", "Anticipate", "Jockey", "Block", "Slide Tackle", "Aerial Fortress",
    # Physical
    "Quick Step", "Relentless", "Bruiser", "Enforcer", "Long Throw",
    # Goalkeeper
    "Far Reach", "Rush Out", "Footwork", "Deflector", "Cross Claimer", "Far Throw",
]
_PS_EXTRA_ALIASES = {
    "lowdriven": "Low Driven Shot", "lowdrivenshot": "Low Driven Shot",
    "finesse": "Finesse Shot", "powershot": "Power Shot", "chip": "Chip Shot",
    "gamechanger": "Gamechanger", "gamechangerplus": "Gamechanger",
    "pinged": "Pinged Pass", "incisive": "Incisive Pass", "tikitaka": "Tiki Taka",
    "longball": "Long Ball Pass", "longballpass": "Long Ball Pass", "whipped": "Whipped Pass",
    "technicaldribbler": "Technical", "quickstep": "Quick Step", "presproven": "Press Proven",
    "slidetackle": "Slide Tackle", "aerialfortress": "Aerial Fortress", "aerial": "Aerial Fortress",
    "acrobatic": "Acrobatic", "deadball": "Dead Ball", "precisionheader": "Precision Header",
}
PLAYSTYLE_ALIASES: Dict[str, str] = {norm_key(p): p for p in PLAYSTYLES}
PLAYSTYLE_ALIASES.update(_PS_EXTRA_ALIASES)


def canonical_playstyle(name: str) -> Optional[str]:
    key = norm_key(name)
    if key.endswith("plus"):
        key = key[:-4]
    return PLAYSTYLE_ALIASES.get(key)


# Position -> position group used by the model.
POSITION_GROUPS = {
    "ST": "ST", "CF": "ST", "LF": "ST", "RF": "ST",
    "LW": "W", "RW": "W", "LM": "W", "RM": "W",
    "CAM": "CAM",
    "CM": "CM", "LCM": "CM", "RCM": "CM",
    "CDM": "CDM",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "CB": "CB", "LCB": "CB", "RCB": "CB",
    "GK": "GK",
}
GROUP_LABELS_NO = {
    "ST": "Spiss", "W": "Kant", "CAM": "CAM", "CM": "CM", "CDM": "CDM",
    "FB": "Back", "CB": "Midtstopper", "GK": "Keeper",
}

GROUP_PLURAL_NO = {
    "ST": "spisser", "W": "kanter", "CAM": "CAM-er", "CM": "CM-er", "CDM": "CDM-er",
    "FB": "backer", "CB": "midtstoppere", "GK": "keepere",
}


_WORK_RATE = {"h": "H", "high": "H", "3": "H", "m": "M", "med": "M", "medium": "M", "2": "M",
              "l": "L", "low": "L", "1": "L"}


def norm_work_rate(value) -> Optional[str]:
    """'High', 'h', 3 -> 'H'. None if unknown."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("label") or value.get("value") or value.get("name")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = int(value)
    return _WORK_RATE.get(re.sub(r"[^a-z0-9]", "", str(value).lower()))


def split_work_rates(text) -> Tuple[Optional[str], Optional[str]]:
    """'H/M' or 'Medium/Medium' -> ('H', 'M')."""
    if not text:
        return None, None
    parts = re.split(r"\s*/\s*", str(text).strip())
    if len(parts) != 2:
        return None, None
    return norm_work_rate(parts[0]), norm_work_rate(parts[1])


def position_group(position: Optional[str]) -> Optional[str]:
    if not position:
        return None
    return POSITION_GROUPS.get(str(position).upper().strip())


# The ten leagues shown first in the league filter (the rest follow alphabetically). Names as on EA's ratings pages.
TOP_LEAGUES = ["Premier League", "LALIGA EA SPORTS", "Serie A Enilive", "Bundesliga", "Ligue 1 McDonald's",
               "ROSHN Saudi League", "Trendyol Süper Lig", "Liga Portugal", "Eredivisie", "MLS"]


def parse_birthdate(v) -> Optional[str]:
    """A date of birth as YYYY-MM-DD, from ISO text ('1994-09-08', '1994-09-08T00:00:00Z'),
    '9/8/1994' or '12/20/1998 0:00' (EA, month first, sometimes with a time), '08.09.1994' or a Unix time in seconds or milliseconds."""
    import re as _re
    from datetime import datetime as _dt, timezone as _tz
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        t = float(v) / (1000.0 if abs(v) > 1e11 else 1.0)
        try:
            return _dt.fromtimestamp(t, _tz.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip()
    m = _re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = _re.match(r"^(\d{1,2})([/.])(\d{1,2})\2(\d{4})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$", s)
        if not m:
            return None
        a, sep, b, y = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        mo, d = (a, b) if sep == "/" and a <= 12 else (b, a)
    try:
        return _dt(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


@dataclass
class Player:
    name: str
    position: str
    attributes: Dict[str, float]
    id: Optional[str] = None
    ovr: Optional[int] = None
    alt_positions: List[str] = field(default_factory=list)
    gender: str = "M"
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    foot: Optional[str] = None
    skill_moves: Optional[int] = None
    weak_foot: Optional[int] = None
    playstyles: List[str] = field(default_factory=list)
    playstyles_plus: List[str] = field(default_factory=list)
    # {"ST": {"Advanced Forward": 2, "Poacher": 1}}  2 = ++, 1 = +, 0 = role without familiarity
    roles: Dict[str, Dict[str, int]] = field(default_factory=dict)
    body_type: Optional[str] = None
    accelerate_source: Optional[str] = None  # AcceleRATE as reported by the data source
    off_balance_dribbling: Optional[float] = None
    rarity: Optional[str] = None
    price: Optional[int] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    playstyles_complete: bool = True
    roles_complete: bool = True
    # Six face stats as shown on the card: {"pac": 87, "sho": ..., "pas", "dri", "def", "phy"}
    face_stats: Dict[str, float] = field(default_factory=dict)
    # "utgitt" (released) or "lekket" (leaked, not confirmed)
    status: Optional[str] = None
    # True when detailed attributes are estimated from base card + face stats
    estimated: bool = False
    base_id: Optional[str] = None
    url: Optional[str] = None
    # Attacking / defensive work rate: "H", "M" or "L". EA replaced work rates with
    # roles in FC 25, but the value is still in the card data.
    work_rate_att: Optional[str] = None
    work_rate_def: Optional[str] = None
    # Club, league and nation (from EA's ratings pages; special cards inherit them from the base card)
    club: Optional[str] = None
    image: Optional[str] = None  # portrait URL (EA), shown on the pages, never downloaded
    league: Optional[str] = None
    nation: Optional[str] = None
    # Date of birth as YYYY-MM-DD (EA's ratings pages; for evos with an age requirement)
    birthdate: Optional[str] = None
    # True for special cards whose PlayStyles are copied from the base card (FIFA Rosters has none):
    # promo cards can have more PlayStyles in the game than we know of.
    ps_from_base: bool = False

    @property
    def uid(self) -> str:
        return "|".join(str(x) for x in (self.name, self.rarity or "", self.id or "", self.status or ""))

    @property
    def groups(self) -> List[str]:
        out: List[str] = []
        for pos in [self.position] + list(self.alt_positions):
            g = position_group(pos)
            if g and g not in out:
                out.append(g)
        return out

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        attrs: Dict[str, float] = {}
        unknown: List[str] = []
        for key, value in (data.get("attributes") or {}).items():
            canon = canonical_attribute(key)
            if canon is None:
                unknown.append(key)
                continue
            if value is None or value == "":
                continue
            if float(value) <= 0:  # some sites show 0 for attributes that don't apply
                continue
            attrs[canon] = float(value)

        def ps_list(values):
            out = []
            for v in values or []:
                c = canonical_playstyle(v)
                if c and c not in out:
                    out.append(c)
            return out

        plus = ps_list(data.get("playstyles_plus"))
        base = [p for p in ps_list(data.get("playstyles")) if p not in plus]

        roles: Dict[str, Dict[str, int]] = {}
        for pos, role_map in (data.get("roles") or {}).items():
            roles[str(pos).upper()] = {str(r): int(v) for r, v in (role_map or {}).items()}

        gender = str(data.get("gender") or "M").upper()[:1]
        if gender not in ("M", "F"):
            gender = "M"

        def num(v):
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def intnum(v):
            n = num(v)
            return int(n) if n is not None else None

        wr_att, wr_def = split_work_rates(data.get("work_rates"))
        wr_att = norm_work_rate(data.get("work_rate_att")) or wr_att
        wr_def = norm_work_rate(data.get("work_rate_def")) or wr_def

        return cls(
            name=str(data.get("name") or "Ukjent"),
            position=str(data.get("position") or "").upper(),
            attributes=attrs,
            id=str(data["id"]) if data.get("id") is not None else None,
            ovr=intnum(data.get("ovr")),
            alt_positions=[str(p).upper() for p in (data.get("alt_positions") or [])],
            gender=gender,
            height_cm=num(data.get("height_cm")),
            weight_kg=num(data.get("weight_kg")),
            foot=data.get("foot"),
            skill_moves=intnum(data.get("skill_moves")),
            weak_foot=intnum(data.get("weak_foot")),
            playstyles=base,
            playstyles_plus=plus,
            roles=roles,
            body_type=data.get("body_type"),
            accelerate_source=data.get("accelerate_source") or data.get("accelerate"),
            off_balance_dribbling=num(data.get("off_balance_dribbling")),
            rarity=data.get("rarity"),
            price=intnum(data.get("price")),
            source=data.get("source"),
            notes=data.get("notes"),
            playstyles_complete=bool(data.get("playstyles_complete", True)),
            roles_complete=bool(data.get("roles_complete", True)),
            face_stats={str(k).lower(): float(v) for k, v in (data.get("face_stats") or {}).items()
                        if v not in (None, "")},
            status=data.get("status"),
            estimated=bool(data.get("estimated", False)),
            base_id=str(data["base_id"]) if data.get("base_id") is not None else None,
            url=data.get("url"),
            club=data.get("club") or None,
            image=(data.get("image") if str(data.get("image") or "").startswith("https://") else None),
            league=data.get("league") or None,
            nation=data.get("nation") or None,
            birthdate=parse_birthdate(data.get("birthdate")),
            ps_from_base=bool(data.get("ps_from_base", False)),
            work_rate_att=wr_att,
            work_rate_def=wr_def,
        )
