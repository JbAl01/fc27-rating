"""FC 27 AcceleRATE classification and Off-Balance Dribbling estimate.

FC 27 has three AcceleRATE types (Explosive, Controlled, Lengthy). The type
is decided from Height, Acceleration, Agility and Strength *after*
chemistry-style boosts. Thresholds live in config/weights.json so they can be
corrected if EA changes them in a title update.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

EXPLOSIVE = "Explosive"
CONTROLLED = "Controlled"
LENGTHY = "Lengthy"


def classify(attrs: Dict[str, float], height_cm: Optional[float], gender: str,
             rules: dict) -> Tuple[Optional[str], str]:
    """Return (type, reason). Type is None if height is unknown and matters."""
    agi = attrs.get("agility")
    strn = attrs.get("strength")
    acc = attrs.get("acceleration")
    if agi is None or strn is None or acc is None:
        return None, "mangler Agility, Strength eller Acceleration"

    sex = "female" if gender == "F" else "male"
    ex = rules["explosive"]
    le = rules["lengthy"]

    explosive_stats = (agi >= ex["min_agility"]
                       and agi - strn >= ex["min_agility_minus_strength"]
                       and acc >= ex["min_acceleration"])
    lengthy_stats = (strn >= le["min_strength"]
                     and strn - agi >= le["min_strength_minus_agility"]
                     and acc >= le["min_acceleration"])

    if height_cm is None:
        if not explosive_stats and not lengthy_stats:
            return CONTROLLED, "statsene passer ikke Explosive eller Lengthy"
        return None, "høyde mangler, og statsene kan gi Explosive eller Lengthy"

    if explosive_stats and height_cm <= ex["max_height_cm"][sex]:
        return EXPLOSIVE, (f"Agility {agi:.0f}, Agility-Strength {agi - strn:+.0f}, "
                           f"Acceleration {acc:.0f}, høyde {height_cm:.0f} cm")
    if lengthy_stats and height_cm >= le["min_height_cm"][sex]:
        return LENGTHY, (f"Strength {strn:.0f}, Strength-Agility {strn - agi:+.0f}, "
                         f"høyde {height_cm:.0f} cm")

    if explosive_stats:
        return CONTROLLED, (f"statsene holder til Explosive, men {height_cm:.0f} cm er over "
                            f"grensen på {ex['max_height_cm'][sex]} cm")
    if lengthy_stats:
        return CONTROLLED, (f"statsene holder til Lengthy, men {height_cm:.0f} cm er under "
                            f"grensen på {le['min_height_cm'][sex]} cm")
    return CONTROLLED, "statsene passer ikke Explosive eller Lengthy"


def off_balance_dribbling(attrs: Dict[str, float], weights: Dict[str, float]) -> Optional[float]:
    """FC 27 Off-Balance Dribbling: weighted average of Agility, Balance and Dribbling
    (equal weights = the plain average, as EasySBC shows it per card)."""
    total = 0.0
    for key, w in weights.items():
        if key not in attrs:
            return None
        total += attrs[key] * w
    wsum = sum(weights.values())
    return round(total / wsum, 1) if wsum else None
