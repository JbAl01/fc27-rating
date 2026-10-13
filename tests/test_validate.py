import tempfile
import unittest
from pathlib import Path

from fcrating import validate


def card(name, igr, feel, run, rarity="Gold", ovr=80, obd=80):
    return {"name": name, "rarity": rarity, "ovr": ovr, "position_group": "ST", "feel": feel,
            "run_ai": {"score": run}, "off_balance_dribbling": obd,
            "by_group": {"ST": {"igr": igr, "pace": 80, "skill": 80}}}


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.results = [card("Alfa", 90, 85, 70), card("Beta", 85, 80, 90), card("Gamma", 80, 75, 80),
                        card("Delta", 75, 70, 60), card("Alfa", 84, 79, 65, rarity="TOTW", ovr=86)]

    def test_find_card_prefers_version_then_highest_ovr(self):
        c, hits = validate.find_card(self.results, "alfa")
        self.assertEqual(len(hits), 2)
        self.assertEqual(c["rarity"], "TOTW")  # highest OVR when no version is given
        c, _ = validate.find_card(self.results, "Alfa|gold")
        self.assertEqual(c["rarity"], "Gold")
        self.assertIsNone(validate.find_card(self.results, "Zulu")[0])

    def test_bradley_terry_orders_by_wins(self):
        pairs = [("A", "B", 1.0), ("A", "C", 1.0), ("B", "C", 1.0), ("A", "B", 1.0)]
        bt = validate.bradley_terry(pairs)
        self.assertGreater(bt["A"], bt["B"])
        self.assertGreater(bt["B"], bt["C"])

    def test_evaluate_counts_agreement_per_part_and_type(self):
        tests = [
            {"a": "Alfa", "a_versjon": "Gold", "b": "Delta", "vinner": "a", "styrke": "3", "type": "alt"},
            {"a": "Beta", "b": "Alfa", "a_versjon": "", "b_versjon": "Gold", "vinner": "a", "styrke": "2", "type": "løp"},
            {"a": "Gamma", "b": "Delta", "vinner": "a", "styrke": "1", "type": "ball"},
            {"a": "Gamma", "b": "Zulu", "vinner": "a", "styrke": "1", "type": "alt"},
        ]
        ev = validate.evaluate(tests, self.results)
        self.assertEqual(ev["decided"], 3)
        self.assertIn("Zulu", ev["missing"])
        comp = {l: p for l, p, _ in ev["comp"]}
        self.assertEqual(comp["Løps-AI"], 100)  # Løps-AI picks every winner here
        self.assertLess(comp["IGR"], 100)       # IGR had Alfa ahead of Beta in the run test
        self.assertEqual({l: p for l, p, _ in ev["by_type"]["uten ball"]}["Løps-AI"], 100)
        self.assertTrue(any("bommet" in line for line in validate.report_lines(ev)))

    def test_add_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tester.csv"
            n = validate.add_test({"dato": "2026-10-13", "a": "Vicky López", "b": "Alfa", "vinner": "a", "styrke": 2}, path)
            n = validate.add_test({"dato": "2026-10-13", "a": "Beta", "b": "Alfa", "vinner": "lik", "styrke": 1}, path)
            self.assertEqual(n, 2)
            rows = validate.load_tests(path)
            self.assertEqual(rows[0]["a"], "Vicky López")
            self.assertEqual(rows[1]["vinner"], "lik")


if __name__ == "__main__":
    unittest.main()
