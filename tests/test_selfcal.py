"""Selvkalibrering: the body offsets follow what people play, at half strength, and the same learned
points reach model.rate and Evo Lab's FastRater."""
import copy
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating import evolab, selfcal  # noqa: E402
from fcrating.model import load_config, rate  # noqa: E402
from fcrating.schema import position_group  # noqa: E402
from fcrating.sources import local  # noqa: E402

CFG = load_config(ROOT / "config")
BASE = local.load_json(str(ROOT / "data" / "eksempel_spillere.json"))


def _results(n=600, seed=3):
    """Wingers: IGR drives use, but Stocky Medium cards are used as if they had 2 points more."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        key = ["lean_medium", "average_medium", "stocky_medium"][i % 3]
        igr = rng.uniform(70, 95)
        true = igr + (2.0 if key == "stocky_medium" else 0.0)
        used = true > 92.5 or (true > 90 and rng.random() < 0.3)
        out.append({"name": f"P{i}", "nation": "X", "gender": "M", "status": None, "ovr": int(igr) - 5, "position": "RW",
                    "position_group": "W", "rarity": "FC 27 Rare Gold",
                    "usage": {"pro": [5.0, "RW"], "com": [3.0, "RW"]} if used else {},
                    "by_group": {"W": {"igr": igr, "top_pct": 100.0 * (95 - igr) / 25, "calibration": 0.0,
                                       "body_detail": {"key": key, "estimated": False, "learn": 0.0}}}})
    return out


class SelfCalTests(unittest.TestCase):
    def test_stocky_used_more_than_igr_says_gets_points_at_half_strength(self):
        res = _results()
        raw, used = selfcal.fit_body(selfcal._rows(res), dict(selfcal.DEFAULTS))
        self.assertGreater(raw["atk"]["stocky_medium"], 0.8)
        self.assertGreater(raw["atk"]["stocky_medium"], raw["atk"]["lean_medium"])
        with tempfile.TemporaryDirectory() as d:
            data = selfcal.update(res, {"weights": {"position_calibration": {"offsets": {}}}}, Path(d) / "k.json", log=lambda *a: None)
        got = data["body"]["atk"]["stocky_medium"]
        self.assertAlmostEqual(got, round(0.5 * raw["atk"]["stocky_medium"], 1), delta=0.11)   # 50/50
        self.assertLessEqual(abs(got), selfcal.DEFAULTS["max_abs"])

    def test_small_change_does_not_move_saved_values(self):
        res = _results()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "k.json"
            first = selfcal.update(res, {"weights": {}}, p, log=lambda *a: None)
            second = selfcal.update(res, {"weights": {}}, p, log=lambda *a: None)
        self.assertEqual(first["body"], second["body"])

    def test_learned_points_same_in_rate_and_fastrater(self):
        cfg = copy.deepcopy(CFG)
        cfg["weights"]["body_profile"]["learned"] = {"atk": {"lean_medium": 0.4, "stocky_tall": -0.3, "unique": 0.2},
                                                     "mid": {"average_short": 0.5}, "def": {"lean_tall": -0.4}}
        bodies = ["Lean Medium", "Stocky Tall", "Kylian Mbappé", "Average Short", "Lean Tall"]
        n = 0
        for i, p in enumerate(copy.deepcopy(p) for p in BASE):
            p.body_type, p.weight_kg = bodies[i % len(bodies)], 72.0
            p.height_cm = p.height_cm or 180.0
            g = position_group(p.position)
            if g == "GK":
                continue
            full = rate(p, cfg, groups=[g])["by_group"][g]
            fast = evolab.FastRater(p, g, cfg).igr(evolab.state_from(p))
            self.assertAlmostEqual(fast, full["igr"], delta=0.051, msg=p.name)   # rate rounds to 0.1
            n += bool(full["body_detail"]["learn"])
        self.assertGreater(n, 0)

    def test_test_list_has_both_parts(self):
        lines = selfcal.test_list(_results())
        self.assertTrue(lines[0].startswith("Spilles mye"))
        self.assertTrue(any(x.startswith("Rangeres høyt") for x in lines))


if __name__ == "__main__":
    unittest.main()
