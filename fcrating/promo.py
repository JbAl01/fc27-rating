"""Build special (promo) cards from base cards.

A promo card is almost always the base card with upgrades. When a source only
gives the six face stats (PAC/SHO/PAS/DRI/DEF/PHY), the upgrade is spread back
over the attributes behind each face stat, using EA's face stat weights. Height,
body type and anything not covered by the face stats come from the base card.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

from .schema import Player, split_work_rates

FACE_KEYS = ["pac", "sho", "pas", "dri", "def", "phy"]
FACE_ALIASES = {
    "pace": "pac", "pac": "pac", "shooting": "sho", "sho": "sho", "passing": "pas", "pas": "pas",
    "dribbling": "dri", "dri": "dri", "defending": "def", "def": "def", "physical": "phy",
    "physicality": "phy", "phy": "phy",
}


def face_from_attributes(attrs: Dict[str, float], face_weights: dict) -> Dict[str, float]:
    out = {}
    for key in FACE_KEYS:
        w = {k: v for k, v in face_weights[key].items() if not k.startswith("_")}
        if all(k in attrs for k in w):
            out[key] = sum(attrs[k] * v for k, v in w.items())
    return out


def _spread(attrs: Dict[str, float], weights: Dict[str, float], target: float) -> None:
    """Shift the attributes behind one face stat so their weighted average hits target.
    Every attribute moves by the same amount; attributes stuck at 1 or 99 hand
    the rest of the shift to the others."""
    keys = [k for k in weights if k in attrs]
    if not keys:
        return
    for _ in range(10):
        current = sum(attrs[k] * weights[k] for k in keys) / sum(weights[k] for k in keys)
        gap = target - current
        if abs(gap) < 0.01:
            break
        free = [k for k in keys if (gap > 0 and attrs[k] < 99) or (gap < 0 and attrs[k] > 1)]
        if not free:
            break
        share = sum(weights[k] for k in free) / sum(weights[k] for k in keys)
        step = gap / share
        for k in free:
            attrs[k] = min(99.0, max(1.0, attrs[k] + step))
    for k in keys:
        attrs[k] = float(round(attrs[k]))


def estimate_attributes(base: Player, face: Dict[str, float], new_ovr: Optional[int],
                        cfg: dict) -> Dict[str, float]:
    """Base attributes moved so the face stats match the promo card."""
    wcfg = cfg["weights"]
    fw = wcfg["face_stats"]
    attrs = dict(base.attributes)
    base_face = {k: v for k, v in base.face_stats.items() if k in FACE_KEYS} or \
        face_from_attributes(attrs, fw)
    for key in FACE_KEYS:
        if key not in face or key not in base_face:
            continue
        delta = face[key] - base_face[key]
        if delta == 0:
            continue
        weights = {k: v for k, v in fw[key].items() if not k.startswith("_")}
        current = sum(attrs[k] * weights[k] for k in weights if k in attrs) / \
            max(1e-9, sum(weights[k] for k in weights if k in attrs))
        _spread(attrs, weights, current + delta)
    if new_ovr is not None and base.ovr is not None and new_ovr > base.ovr:
        bump = round((new_ovr - base.ovr) * wcfg["promo"]["reactions_composure_per_ovr"])
        for k in ("reactions", "composure"):
            if k in attrs:
                attrs[k] = float(min(99, attrs[k] + bump))
    return attrs


# ---------------------------------------------------------------- name matching

_TRANSLIT = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "ß": "ss", "ł": "l", "Ł": "l",
                           "đ": "d", "Đ": "d", "ı": "i", "œ": "oe", "Œ": "oe", "ð": "d", "þ": "th"})


def norm_name(name: str) -> str:
    s = (name or "").translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s.lower())
    return re.sub(r"[^a-z ]", "", s).strip()


BASE_OVR_GAP = 8      # a player's new base card is rarely more than this far from the old one
SPECIAL_OVR_DROP = 2  # a special card is almost never lower than the player's base card


def namesake_reason(cand: Player, player_id: str, ovr: Optional[int], foot: Optional[str],
                    base_card: bool, other_ids: Optional[set]) -> str:
    """Why a name match with another player id is a different player, or '' if it may be the same."""
    if cand.id and other_ids and str(cand.id) != player_id and str(cand.id) in other_ids:
        return f"navnebror (basekortet med samme navn har id {cand.id})"
    f1, f2 = (foot or "").strip().lower()[:1], (cand.foot or "").strip().lower()[:1]
    if f1 and f2 and f1 != f2:
        return "navnebror (annen fot)"
    if ovr is not None and cand.ovr is not None:
        if base_card and abs(cand.ovr - ovr) > BASE_OVR_GAP:
            return f"navnebror (OVR {ovr} mot {cand.ovr:.0f})"
        if not base_card and cand.ovr > ovr + SPECIAL_OVR_DROP:
            return f"navnebror (OVR {ovr} mot {cand.ovr:.0f})"
    return ""


class BaseIndex:
    """Look up base cards by EA player id or by name."""

    def __init__(self, base_players: Iterable[Player]):
        self.by_id: Dict[str, Player] = {}
        self.by_name: Dict[str, List[Player]] = {}
        self.by_last: Dict[str, List[Player]] = {}
        for p in base_players:
            if p.id:
                self.by_id.setdefault(str(p.id), p)
            n = norm_name(p.name)
            if n:
                self.by_name.setdefault(n, []).append(p)
                self.by_last.setdefault(n.split()[-1], []).append(p)

    def find(self, name: str = "", player_id: Optional[str] = None,
             max_ovr: Optional[int] = None, exact_name: bool = False,
             ovr: Optional[int] = None, foot: Optional[str] = None, base_card: bool = False,
             other_ids: Optional[set] = None) -> Tuple[Optional[Player], str]:
        """By EA id first, then by name. With exact_name, only a full-name match
        is accepted (used when the source has an id that EA's base list lacks).

        A name match for a card whose own player id is unknown can be a namesake
        (two players called Bruno Fernandes). It is turned down when the base card's
        id belongs to another player in the source (other_ids), when the preferred
        foot differs, or when the OVR doesn't fit (ovr: the card's OVR; base_card:
        the card is the same player's new base card, so the OVR is close)."""
        if player_id and str(player_id) in self.by_id:
            return self.by_id[str(player_id)], "id"
        n = norm_name(name)
        if not n:
            return None, "mangler navn"
        cands = self.by_name.get(n, [])
        how = "navn"
        if exact_name and len(cands) != 1:
            return None, "fant ikke basekortet"
        if exact_name and player_id:
            why = namesake_reason(cands[0], str(player_id), ovr, foot, base_card, other_ids)
            if why:
                return None, why
        if not cands:
            parts = n.split()
            last = self.by_last.get(parts[-1], [])
            if len(parts) > 1:
                last = [p for p in last if norm_name(p.name).split()[0][:1] == parts[0][:1]] or \
                    [p for p in last if len(norm_name(p.name).split()) == 1]
            cands, how = last, "etternavn"
        if max_ovr is not None:
            cands = [p for p in cands if p.ovr is None or p.ovr <= max_ovr] or cands
        if not cands:
            return None, "fant ikke basekortet"
        if len(cands) > 1:
            cands = sorted(cands, key=lambda p: p.ovr or 0, reverse=True)
            return cands[0], f"{how} (valgte høyeste av {len(cands)})"
        return cands[0], how


# ---------------------------------------------------------------- building cards

def special_roles(positions: List[str], level: int) -> Dict[str, Dict[str, int]]:
    """EA: special items get Role++ in every role of their primary and secondary positions."""
    return {pos: {"alle roller (spesialkort)": level} for pos in positions if pos}


def build_special(base: Optional[Player], *, name: str, version: str, ovr: Optional[int],
                  face: Dict[str, float], cfg: dict, position: Optional[str] = None,
                  attributes: Optional[Dict[str, float]] = None, ps_plus: Iterable[str] = (),
                  status: str = "utgitt", card_id: Optional[str] = None, url: Optional[str] = None,
                  height_cm: Optional[float] = None, skill_moves: Optional[int] = None,
                  weak_foot: Optional[int] = None, source: str = "",
                  work_rates: Optional[str] = None, special: bool = True) -> Optional[Player]:
    """Return a Player for a special card, or None if there is nothing to build from."""
    if attributes:
        p = copy.deepcopy(base) if base else Player(name=name, position=position or "", attributes={})
        p.attributes = dict(attributes)
        if base:
            # keep base values for attributes the source doesn't show (e.g. Composure)
            for k, v in base.attributes.items():
                p.attributes.setdefault(k, v)
        p.estimated = False
    elif base:
        p = copy.deepcopy(base)
        p.attributes = estimate_attributes(base, face, ovr, cfg)
        p.estimated = True
    else:
        return None

    p.name = base.name if base else name
    p.rarity = version
    p.ovr = ovr if ovr is not None else p.ovr
    if position:
        p.position = position
        p.alt_positions = [a for a in (base.alt_positions if base else []) if a != position]
        if base and base.position != position and base.position not in p.alt_positions:
            p.alt_positions.append(base.position)
    p.face_stats = dict(face)
    p.status = status
    p.id = str(card_id) if card_id else None
    p.base_id = base.id if base else None
    p.ps_from_base = bool(special and base)
    p.url = url
    p.source = source
    p.price = None
    if height_cm:
        p.height_cm = height_cm
    if skill_moves:
        p.skill_moves = skill_moves
    if weak_foot:
        p.weak_foot = weak_foot
    wr_att, wr_def = split_work_rates(work_rates)
    if wr_att:
        p.work_rate_att, p.work_rate_def = wr_att, wr_def
    for ps in ps_plus:
        if ps and ps not in p.playstyles_plus:
            p.playstyles_plus.append(ps)
        if ps in p.playstyles:
            p.playstyles.remove(ps)
    if special:  # special items get ++ in every role; base cards keep what the source says
        level = cfg["weights"]["promo"]["special_items_role_level"]
        p.roles = special_roles([p.position] + list(p.alt_positions), level)
        p.roles_complete = True
    p.accelerate_source = None  # recomputed from the new attributes
    return p


def drop_released_leaks(cards: List[Player]) -> List[Player]:
    """A leak is dropped once a released card for the same player with the same OVR exists."""
    released = {(norm_name(c.name), c.ovr) for c in cards if c.status != "lekket"}
    return [c for c in cards if c.status != "lekket" or (norm_name(c.name), c.ovr) not in released]
