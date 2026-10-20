"""Skjulte perler (20.10, owner: Dembélé is no hidden gem): a card whose OVR alone puts it in the top of the
position, or that the pros and FUT.GG teams play, is not hidden, however much it beats cards with the same OVR."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating.gems import add_gems, not_hidden_when_used  # noqa: E402

CFG = {"weights": {"blend": {"ST": {"skill": 1.0}},
                   "hidden_gem": {"ovr_window": 1, "min_same_ovr": 8, "min_pool_size": 30, "max_top_pct": 5,
                                  "min_res": 4.0, "min_part": 0.5, "ovr_not_top_pct": 2}}}


def pool():
    cards = []
    for i in range(300):   # 300 cards from OVR 60 to 89, IGR = OVR
        o = 60 + i % 30
        cards.append({"name": f"K{i}", "ovr": o, "by_group": {"ST": {"igr": float(o), "skill": float(o)}}})
    top = {"name": "Topp", "ovr": 90, "by_group": {"ST": {"igr": 105.0, "skill": 105.0}}}
    low = {"name": "Lav", "ovr": 72, "by_group": {"ST": {"igr": 84.0, "skill": 84.0}}}
    used = {"name": "Brukt", "ovr": 73, "by_group": {"ST": {"igr": 85.0, "skill": 85.0}}, "usage": {"pro": [9.0, "ST"]}}
    for o in range(88, 91):   # enough cards around 90 to compare with (OVR 90+: 4 of 312, top 1.3 %)
        cards += [{"name": f"T{o}{j}", "ovr": o, "by_group": {"ST": {"igr": float(o), "skill": float(o)}}} for j in range(3)]
    return cards + [top, low, used], top, low, used


class HiddenGemTests(unittest.TestCase):
    def test_top_ovr_and_used_cards_are_not_hidden(self):
        cards, top, low, used = pool()
        add_gems({"ST": cards}, CFG)
        self.assertGreater(top["by_group"]["ST"]["gem"]["res"], 10)   # far above cards with the same OVR ...
        self.assertFalse(top["by_group"]["ST"]["gem"]["on"])          # ... but the OVR already shows it
        self.assertTrue(low["by_group"]["ST"]["gem"]["on"])
        self.assertTrue(used["by_group"]["ST"]["gem"]["on"])
        not_hidden_when_used(cards)
        self.assertFalse(used["by_group"]["ST"]["gem"]["on"])         # known: the pros play it
        self.assertTrue(low["by_group"]["ST"]["gem"]["on"])


if __name__ == "__main__":
    unittest.main()
