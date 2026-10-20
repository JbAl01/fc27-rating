"""Vanskelig å stoppe: how hard a card is to stop once it is going.

Two parts, both on the attribute scale like OVR:

  * med ball  - carrying the ball at speed: shoulder challenges, tackles from behind and
                the side, knock-ons. Strength and Balance keep the player up and on the
                ball, Sprint Speed and Acceleration keep the defender behind, Ball Control
                and Dribbling keep the ball close so a touch does not run away.
  * uten ball - on a run without the ball: how hard the defender finds it to catch the
                runner and knock him off before the pass arrives. Sprint Speed and
                Strength first, then Acceleration, Balance and Stamina.

What it builds on (things that have held across many FIFA/FC years, not one game's quirk):

  * Physical duels and shielding: Strength decides shoulder-to-shoulder duels and
    shielding, Balance whether the player stays upright and keeps going.
  * The pace-and-power meta of every year: players who are both fast and strong
    (min of Sprint Speed and Strength, "rask og sterk") were the hardest to stop.
  * AcceleRATE (FIFA 23 onward): Lengthy players need longer to get going but catch up
    with or pass anyone over distance, so on a long run they are the hardest to catch.
  * PlayStyles (FC 24-27, EA): Rapid keeps top speed longer and makes fewer mistakes
    when sprint dribbling, Press Proven and Enforcer shield better and hold off
    stronger players, Bruiser adds strength in physical challenges (smaller in FC 27).
  * FC 27 off-balance dribbling (Agility, Balance, Dribbling) is already inside the
    attributes here, and gives its own bonus in IGR.

The weights are start values in config/weights.json under "hard_to_stop".
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple


def _clean(d: dict) -> dict:
    return {k: v for k, v in (d or {}).items() if not str(k).startswith("_")}


def features(attrs: Dict[str, float]) -> Dict[str, float]:
    f = {k: float(v) for k, v in attrs.items() if v}
    if f.get("sprint_speed") and f.get("strength"):
        f["rask_sterk"] = min(f["sprint_speed"], f["strength"])
    return f


def ps_bonus(table: dict, ps: Iterable[str], psp: Iterable[str], cap: float) -> float:
    """PS / PS+ points from the table, in config order, added with a plain loop (the page does the same)."""
    ps, psp = set(ps or []), set(psp or [])
    total = 0.0
    for name, (base, plus) in _clean(table).items():
        if name in psp:
            total += plus
        elif name in ps:
            total += base
    return min(total, cap)


def scores(attrs: Dict[str, float], acc_type: Optional[str], ps: Iterable[str], psp: Iterable[str],
           cfg: dict) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(Vanskelig å stoppe, med ball, uten ball). None when the config has no hard_to_stop
    section or the card misses too many attributes."""
    from .runs import score
    c = cfg["weights"].get("hard_to_stop")
    if not c:
        return None, None, None
    f = features(attrs)
    ball0 = score(f, _clean(c["ball"]))[0]
    run0 = score(f, _clean(c["run"]))[0]
    if ball0 is None or run0 is None:
        return None, None, None
    ball = round(ball0 + ps_bonus(c.get("playstyles_ball"), ps, psp, c.get("ps_cap_ball", 4.0)), 1)
    run = round(run0 + _clean(c.get("accelerate_run")).get(acc_type or "", 0.0)
                + ps_bonus(c.get("playstyles_run"), ps, psp, c.get("ps_cap_run", 1.5)), 1)
    share = c.get("ball_share", 0.5)
    return round(share * ball + (1 - share) * run, 1), ball, run


def core(attrs: Dict[str, float], acc_type: Optional[str], cfg: dict) -> Optional[float]:
    """Vanskelig å stoppe without the PlayStyles: the part that goes into IGR. The PlayStyles (Rapid, Press Proven,
    Enforcer, Bruiser, Quick Step) are counted once, in their own PlayStyle value; the number shown on the page
    keeps them, because that is what makes the card hard to stop."""
    s = scores(attrs, acc_type, (), (), cfg)
    return s[0]
