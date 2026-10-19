"""Meta: IGR measured against the cards that exist now (drops when better cards arrive)."""
import json
import tempfile
import unittest
from pathlib import Path

from fcrating import meta

CFG = {"weights": {"meta": {"top": 3, "min_pool": 3}}}


def card(igr, group="ST", status=""):
    return {"status": status, "position_group": group, "by_group": {group: {"igr": igr}}}


class MetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "meta_start.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_level_is_average_of_best_and_ignores_leaks(self):
        cards = [card(90), card(88), card(86), card(70), card(99, status="lekket")]
        self.assertEqual(meta.levels(cards, CFG), {"ST": 88.0})

    def test_small_positions_are_skipped(self):
        self.assertEqual(meta.levels([card(90, "GK"), card(80, "GK")], CFG), {})

    def test_without_start_meta_equals_igr_and_nothing_is_saved(self):
        cards = [card(90), card(88), card(86)]
        info = meta.apply(cards, CFG, path=self.path)
        self.assertEqual([c["by_group"]["ST"]["meta"] for c in cards], [90, 88, 86])
        self.assertFalse(self.path.exists())
        self.assertIsNone(info["since"])

    def test_first_save_then_better_cards_lower_meta(self):
        gold = card(90)
        cards = [gold, card(88), card(86)]
        info = meta.apply(cards, CFG, path=self.path, save=True)
        self.assertTrue(info["saved"])
        self.assertEqual(gold["by_group"]["ST"]["meta"], 90)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["levels"], {"ST": 88.0})

        # four months later: three promo strikers far better than the old top
        gold2 = card(90)
        later = [gold2, card(88), card(86), card(95), card(94), card(93)]
        info = meta.apply(later, CFG, path=self.path, save=True)
        self.assertFalse(info["saved"])  # start level is kept, not overwritten
        self.assertEqual(info["groups"]["ST"]["drift"], 6.0)  # level 94 now vs 88 at start
        self.assertEqual(gold2["by_group"]["ST"]["meta"], 84.0)
        self.assertEqual(gold2["pos_meta"], 84.0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["levels"], {"ST": 88.0})

    def test_meta_never_rises_above_igr(self):
        meta.save_start({"since": "2026-10-14", "levels": {"ST": 95.0}}, self.path)
        cards = [card(90), card(88), card(86)]
        meta.apply(cards, CFG, path=self.path)
        self.assertEqual(cards[0]["by_group"]["ST"]["meta"], 90)

    def test_new_position_is_added_to_start_without_touching_others(self):
        meta.save_start({"since": "2026-10-14", "levels": {"ST": 80.0}}, self.path)
        cards = [card(90), card(88), card(86), card(85, "CB"), card(84, "CB"), card(83, "CB")]
        info = meta.apply(cards, CFG, path=self.path, save=True)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["levels"], {"ST": 80.0, "CB": 84.0})
        self.assertEqual(saved["since"], "2026-10-14")
        self.assertEqual(info["groups"]["ST"]["drift"], 8.0)
        self.assertEqual(info["groups"]["CB"]["drift"], 0.0)


class MetaStartCardsTests(unittest.TestCase):
    """The start keeps the cards, so a new IGR formula is not mistaken for the meta moving."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "meta_start.json"

    def tearDown(self):
        self.tmp.cleanup()

    def cards(self, shift=0.0, extra=()):
        out = [dict(card(90 + shift), uid="a"), dict(card(88 + shift), uid="b"), dict(card(86 + shift), uid="c")]
        return out + [dict(card(v), uid=u) for u, v in extra]

    def test_new_formula_does_not_move_meta(self):
        meta.apply(self.cards(), CFG, path=self.path, save=True)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(saved["cards"]["ST"]), ["a", "b", "c"])
        later = self.cards(shift=3.0)   # every card 3 higher: a new formula, no new cards
        info = meta.apply(later, CFG, path=self.path, save=True)
        self.assertEqual(info["groups"]["ST"]["drift"], 0.0)
        self.assertEqual(later[0]["by_group"]["ST"]["meta"], 93.0)

    def test_new_better_cards_still_move_meta(self):
        meta.apply(self.cards(), CFG, path=self.path, save=True)
        later = self.cards(shift=3.0, extra=[("x", 99.0), ("y", 98.0), ("z", 97.0)])
        info = meta.apply(later, CFG, path=self.path, save=True)
        self.assertEqual(info["groups"]["ST"]["drift"], 7.0)   # 98 now vs 91 for the start cards today


class MetaPageTests(unittest.TestCase):
    def test_report_has_meta_column_and_data(self):
        from fcrating.cli import main
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as d:
            main(["rate", str(root / "data" / "eksempel_spillere.json"), "--out", d, "--top", "1", "--uten-evolab"])
            page = (Path(d) / "rapport.html").read_text(encoding="utf-8")
            self.assertIn('data-k="meta"', page)
            self.assertIn('"meta":{"since"', page)
            csv_head = (Path(d) / "ratings.csv").read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertIn("pos_meta", csv_head)


if __name__ == "__main__":
    unittest.main()
