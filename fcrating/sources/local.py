"""Load players from local JSON / CSV files, or from text copied off a player page."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from ..schema import Player, canonical_attribute, canonical_playstyle, norm_key


def load_json(path: str) -> List[Player]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("players", [])
    return [Player.from_dict(d) for d in data]


def save_json(players: List[Player], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"players": [p.to_dict() for p in players]}, f, ensure_ascii=False, indent=2)


def _split_list(value: str) -> List[str]:
    return [v.strip() for v in re.split(r"[;,|]", value or "") if v.strip()]


def load_csv(path: str) -> List[Player]:
    """CSV with one row per player. Attribute columns can use any common name
    ('Sprint Speed', 'sprint_speed', 'sprintSpeed'). PlayStyles go in a column
    'playstyles' separated by ';' with '+' after PlayStyle+ names."""
    players: List[Player] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
        for row in csv.DictReader(f, dialect=dialect):
            attrs: Dict[str, float] = {}
            meta: Dict[str, str] = {}
            for col, val in row.items():
                if col is None or val is None or str(val).strip() == "":
                    continue
                canon = canonical_attribute(col)
                if canon:
                    try:
                        attrs[canon] = float(val)
                    except ValueError:
                        pass
                else:
                    meta[norm_key(col)] = str(val).strip()
            plus, base = [], []
            for ps in _split_list(meta.get("playstyles", "")):
                (plus if ps.endswith("+") else base).append(ps.rstrip("+"))
            plus += _split_list(meta.get("playstylesplus", ""))
            players.append(Player.from_dict({
                "name": meta.get("name") or meta.get("playername"),
                "id": meta.get("id"),
                "ovr": meta.get("ovr") or meta.get("overall") or meta.get("rating"),
                "position": meta.get("position") or meta.get("pos"),
                "alt_positions": _split_list(meta.get("altpositions", "")),
                "gender": meta.get("gender", "M"),
                "height_cm": _parse_height(meta.get("height", "")) or meta.get("heightcm"),
                "weight_kg": _parse_weight(meta.get("weight", "")) or meta.get("weightkg"),
                "foot": meta.get("foot") or meta.get("preferredfoot"),
                "skill_moves": meta.get("skillmoves") or meta.get("sm"),
                "weak_foot": meta.get("weakfoot") or meta.get("wf"),
                "accelerate_source": meta.get("accelerate"),
                "body_type": meta.get("bodytype"),
                "rarity": meta.get("rarity"),
                "price": meta.get("price"),
                "attributes": attrs,
                "playstyles": base,
                "playstyles_plus": plus,
                "source": f"csv:{Path(path).name}",
            }))
    return players


def load_any(path: str) -> List[Player]:
    if str(path).lower().endswith(".csv"):
        return load_csv(path)
    return load_json(path)


# ---------------------------------------------------------------- pasted text

def _parse_height(text: str) -> Optional[float]:
    m = re.search(r"(\d{3})\s*cm", text or "", re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d)\s*'\s*(\d{1,2})", text or "")
    if m:
        # feet/inches is ambiguous by ~2 cm; round down (6'0" -> 182, which matches
        # EA's Explosive cut-off). Prefer sources that give centimetres.
        return float(int((int(m.group(1)) * 12 + int(m.group(2))) * 2.54))
    return None


def _parse_weight(text: str) -> Optional[float]:
    m = re.search(r"(\d{2,3})\s*kg", text or "", re.I)
    return float(m.group(1)) if m else None


def _stars_or_digit(flat: str, label: str) -> Optional[int]:
    """'Skill Moves 4', 'Skill Moves: 4', 'Weak Foot: ✮✮✮✮' or 'Weak4' -> 4."""
    m = re.search(rf"(?:{label})\s*:?\s*(\d)(?!\d)", flat, re.I)
    if m:
        return int(m.group(1))
    m = re.search(rf"(?:{label})\s*:?\s*([✮★⭐☆*]{{1,5}})", flat, re.I)
    if m:
        return sum(1 for c in m.group(1) if c in "✮★⭐*")
    return None


# label, optional chem delta like "6▲", then the value
_LABEL_VALUE = re.compile(
    r"([A-Za-z][A-Za-z\.\' ]{1,30}?)\s*:?\s*(?:\d{1,2}\s*[▲▼↑]\s*)?(\d{1,2})(?![\d\.,])"
)


def parse_page_text(text: str) -> dict:
    """Parse attributes and card info from text copied off a player page
    (EA ratings, FUT.GG, EasySBC ...). Select all on the page, copy, paste
    into a .txt file. Values shown after a chemistry style are the boosted
    values, so copy the page with no chemistry style selected."""
    attrs: Dict[str, float] = {}
    for m in _LABEL_VALUE.finditer(text):
        label = m.group(1).strip()
        canon = canonical_attribute(label)
        if not canon:
            # labels like "Def. Aware." may have trailing words, try the last 3 words
            words = label.split()
            for n in (3, 2, 1):
                canon = canonical_attribute(" ".join(words[-n:])) if len(words) >= n else None
                if canon:
                    break
        if canon and float(m.group(2)) > 0:  # 0 = not used for this player (e.g. GK attributes)
            attrs[canon] = float(m.group(2))  # last occurrence wins (face 'Dribbling' comes first)

    info: dict = {"attributes": attrs}
    flat = re.sub(r"\s+", " ", text)
    m = re.search(r"Height\s*:?\s*(\d{3}\s*cm|\d\s*'\s*\d{1,2})", flat, re.I)
    info["height_cm"] = _parse_height(m.group(1)) if m else None
    m = re.search(r"Weight\s*:?\s*(\d{2,3})\s*kg", flat, re.I)
    info["weight_kg"] = float(m.group(1)) if m and float(m.group(1)) > 0 else None
    wr = re.search(r"Work\s*-?\s*rates?\s*:?\s*(High|Medium|Low|Med|H|M|L)\s*/\s*(High|Medium|Low|Med|H|M|L)\b", flat, re.I)
    if wr:
        info["work_rates"] = f"{wr.group(1)}/{wr.group(2)}"
    info["skill_moves"] = _stars_or_digit(flat, r"Skill Moves|Skill")
    info["weak_foot"] = _stars_or_digit(flat, r"Weak Foot|Weak")
    m = re.search(r"Off[\s-]*Balance(?:\s*Dribbling)?\s*:?\s*(\d{2,3}(?:[.,]\d)?)", flat, re.I)
    info["off_balance_dribbling"] = float(m.group(1).replace(",", ".")) if m else None
    m = re.search(r"AcceleRATE\s*:?\s*(Explosive|Controlled|Lengthy)", flat, re.I)
    info["accelerate_source"] = m.group(1).capitalize() if m else None
    m = re.search(r"(?:Preferred )?Foot\s*:?\s*(Left|Right)", flat, re.I)
    info["foot"] = m.group(1).capitalize() if m else None
    m = re.search(r"Body Type\s*([A-Za-z][A-Za-z ]*?)\s*(?:[-•|]|Real Face|Age\b|Player ID|$)", flat)
    info["body_type"] = m.group(1).strip() if m else None
    return info


def player_from_text(text: str, name: str, position: str, **overrides) -> Player:
    info = parse_page_text(text)
    data = {"name": name, "position": position, **info}
    for k, v in overrides.items():
        if v not in (None, "", []):
            data[k] = v
    return Player.from_dict(data)


def split_playstyles(values: List[str]):
    plus, base = [], []
    for v in values or []:
        name = canonical_playstyle(v.rstrip("+"))
        if not name:
            continue
        (plus if v.strip().endswith("+") else base).append(name)
    return plus, base
