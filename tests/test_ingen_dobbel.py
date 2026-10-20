"""Vakttester: every effect is counted once in IGR (owner 20.10: no double counting, consistent model).

- Height: only in the feel score (EA: animation speed). The body type's size class (Short/Medium/Tall) gives no
  extra points outside centre back (reach).
- Acceleration and AcceleRATE: only in pace, not in the feel score.
- PlayStyles: only in their own PlayStyle value; 'vanskelig å stoppe' goes into IGR without them, and the body
  combinations are for PlayStyles that really interact with a body (not Press Proven, which helps every body).
- A body with a reputation is judged as itself: no generic unique bonus on top.
- Agility on the body: one amplification (agility_amp), not two.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating.body import BodyCard  # noqa: E402
from fcrating.model import load_config, rate  # noqa: E402
from fcrating.schema import position_group  # noqa: E402
from fcrating.sources import local  # noqa: E402

CFG = load_config(ROOT / "config")
BASE = local.load_json(str(ROOT / "data" / "eksempel_spillere.json"))
BP = CFG["weights"]["body_profile"]


def card(body="Average Medium", h=178.0, w=72.0, name="Test", g="W", **attrs):
    p = copy.deepcopy(next(q for q in BASE if position_group(q.position) == "W"))   # the group only matters to BodyCard
    p.name, p.nation, p.rarity, p.body_type, p.height_cm, p.weight_kg = name, "X", "FC 27 Rare Gold", body, h, w
    p.attributes.update(attrs)
    return p


class NoDoubleCountingTests(unittest.TestCase):
    def test_height_counts_only_in_feel(self):
        for g in ("W", "ST", "CAM", "CM", "CDM", "FB"):
            for build in ("Lean", "Average", "Stocky"):
                pts = {s: BodyCard(card(f"{build} {s}", g=g), g, BP).points(card(g=g).attributes, [], [])
                       for s in ("Short", "Medium", "Tall")}
                self.assertEqual(len(set(round(v, 6) for v in pts.values())), 1, (g, build, pts))

    def test_acceleration_and_accelerate_are_pace_not_feel(self):
        slow, fast = card(acceleration=60), card(acceleration=97)
        self.assertEqual(rate(slow, CFG)["feel"], rate(fast, CFG)["feel"])
        self.assertTrue(all(v == 0 for k, v in CFG["weights"]["feel"]["accelerate"].items() if not k.startswith("_")))
        self.assertNotIn("acceleration", CFG["weights"]["feel"]["attributes"])

    def test_press_proven_only_in_its_playstyle_value(self):
        a, b = card(), card()
        b.playstyles_plus = list(b.playstyles_plus) + ["Press Proven"]
        bc = BodyCard(a, "W", BP)
        self.assertEqual(bc.points(a.attributes, a.playstyles, a.playstyles_plus),
                         bc.points(b.attributes, b.playstyles, b.playstyles_plus))
        ra, rb = rate(a, CFG)["by_group"]["W"], rate(b, CFG)["by_group"]["W"]
        self.assertEqual(ra["stop_score"], rb["stop_score"])          # the stop part of IGR leaves PlayStyles out
        self.assertGreater(rb["playstyles"], ra["playstyles"])        # ... they count here, once

    def test_stop_playstyles_still_show_on_the_page(self):
        a, b = card(), card()
        b.playstyles_plus = list(b.playstyles_plus) + ["Rapid"]
        self.assertGreater(rate(b, CFG)["hard_to_stop"]["score"], rate(a, CFG)["hard_to_stop"]["score"])

    def test_reputation_replaces_the_generic_unique_bonus(self):
        bp = copy.deepcopy(BP)
        bp.pop("learned", None)
        bp["reputation"] = {"points": {"Kjent Unik": 1.5}}
        known, plain = card("Kjent Unik", name="Kjent Unik"), card("Annen Unik", name="Annen Unik")
        k = BodyCard(known, "W", bp)
        u = BodyCard(plain, "W", bp)
        std = BodyCard(card("Average Medium"), "W", bp)   # 178 cm, 72 kg is read as Average Medium
        self.assertAlmostEqual(k.amp, std.amp)            # no unique bonus on top of the reputation
        self.assertGreater(u.amp, std.amp)                # the generic bonus for a unique model without one

    def test_one_amplification_of_agility(self):
        bc = BodyCard(card("Lean Medium"), "W", BP)
        self.assertEqual(bc.flex, 0.0)
        self.assertNotIn("flex", BP)


if __name__ == "__main__":
    unittest.main()
