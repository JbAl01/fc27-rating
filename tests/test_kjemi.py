"""Kjemistil for fart (22.10): the pace per style is exact, the AcceleRATE per style comes from FUT.GG's card page."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating.chem import acc_bonus, pace_choices  # noqa: E402
from fcrating.model import load_config  # noqa: E402
from fcrating.sources.futgg import accelerate_by_chem  # noqa: E402

CFG = load_config(ROOT / "config")


class ChemPaceTests(unittest.TestCase):
    def test_pace_boosts_match_futgg_pac(self):
        for st, pac in (("Hunter", 6.0), ("Anchor", 3.0), ("Basic", 1.7), ("Finisher", 0.0)):
            b = CFG["chem"]["styles"][st]["pace"]
            self.assertAlmostEqual(0.45 * b["acceleration"] + 0.55 * b["sprint_speed"], pac, delta=0.06, msg=st)

    def test_explosive_hunter_beats_lengthy_shadow_at_equal_boost(self):
        attrs = {"acceleration": 85, "sprint_speed": 85}
        r = pace_choices(attrs, {"Hunter": "Explosive", "Shadow": "Lengthy", "Finisher": "Explosive"}, "W", CFG)
        self.assertEqual(r["best"][0][0], "Hunter")
        self.assertEqual(r["types"], {"Explosive": ["Finisher", "Hunter"], "Lengthy": ["Shadow"]})
        self.assertIsNone(pace_choices(attrs, {}, "W", CFG))

    def test_mixed_types_lie_between(self):
        t = CFG["weights"]["pace"]["accelerate"]
        self.assertLess(acc_bonus("Controlled", t), acc_bonus("Mostly Explosive", t))
        self.assertLess(acc_bonus("Mostly Explosive", t), acc_bonus("Explosive", t))

    def test_reads_only_this_cards_block(self):
        other = 'accelerateTypes:$R[1]={lengthy:$R[2]=["Hunter"]},hasDynamic:!1,url:"/players/1-x/27-1/",'
        mine = 'accelerateTypes:$R[3]={explosive:$R[4]=["Hunter","Shadow"],controlled:$R[5]=["Sniper"]},hasDynamic:!1,url:"/players/2-y/27-2/",'
        self.assertEqual(accelerate_by_chem(other + mine, "2"), {"Hunter": "Explosive", "Shadow": "Explosive", "Sniper": "Controlled"})


if __name__ == "__main__":
    unittest.main()
