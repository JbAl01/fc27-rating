"""Chemistry styles by purpose (owner 22.10). For now speed: which styles give the card the most pace, and the
AcceleRATE each style gives it (FUT.GG works that out per card from the boosted attributes). The pace boosts per
style are exact (config/chem_styles.json "pace"); the other boosts per attribute are not known yet, so feel and
IGR per style come when they are."""
from __future__ import annotations

from typing import Dict, List, Optional

# FUT.GG's seven AcceleRATE types on our pace scale: the three in weights.json pace.accelerate, the mixed types
# in between (equal steps)
ACC_STEPS = ["Lengthy", "Mostly Lengthy", "Controlled Lengthy", "Controlled", "Controlled Explosive", "Mostly Explosive", "Explosive"]


def acc_bonus(t: str, table: Dict[str, float]) -> float:
    if t in table:
        return float(table[t])
    if t not in ACC_STEPS:
        return 0.0
    i = ACC_STEPS.index(t)
    lo, mid, hi = float(table.get("Lengthy", 0)), float(table.get("Controlled", 0)), float(table.get("Explosive", 0))
    return lo + (mid - lo) * i / 3 if i <= 3 else mid + (hi - mid) * (i - 3) / 3


def pace_choices(attrs: Dict[str, float], chem_acc: Dict[str, str], group: Optional[str], cfg: dict,
                 top: int = 3) -> Optional[dict]:
    """{"best": [[style, AcceleRATE, pace], ...], "types": {AcceleRATE: [styles]}} or None (no data / keeper)."""
    if not chem_acc or not group or group == "GK":
        return None
    styles = (cfg.get("chem") or {}).get("styles") or {}
    pcfg = cfg["weights"]["pace"]
    share = pcfg["acceleration_share"].get(group, pcfg["acceleration_share"]["default"])
    table = {k: v for k, v in pcfg["accelerate"].items() if not k.startswith("_")}
    a, s = attrs.get("acceleration"), attrs.get("sprint_speed")
    if a is None or s is None:
        return None
    rows: List[list] = []
    types: Dict[str, List[str]] = {}
    for st, t in chem_acc.items():
        boost = (styles.get(st) or {}).get("pace") or {}
        aa = min(99.0, a + boost.get("acceleration", 0))
        ss = min(99.0, s + boost.get("sprint_speed", 0))
        rows.append([st, t, round(share * aa + (1 - share) * ss + acc_bonus(t, table), 1)])
        types.setdefault(t, []).append(st)
    rows.sort(key=lambda x: (-x[2], x[0]))
    main = max(types, key=lambda t: len(types[t]))
    # only the styles that give another AcceleRATE than most of them (the ones worth knowing about)
    return {"best": rows[:top], "main": main, "types": {t: sorted(v) for t, v in types.items() if t != main}}
