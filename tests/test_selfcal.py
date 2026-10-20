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


class BodyModelTwoTests(unittest.TestCase):
    """20.10: the body amplifies (a lean body pays in full only on an agile card), known bodies get points
    whatever the numbers, and a unique model gets nothing for being unique."""

    def _card(self, name="Test", body="Lean Medium", agi=90, nation="X", rarity="FC 27 Rare Gold"):
        import copy as _c
        p = _c.deepcopy(next(q for q in BASE if position_group(q.position) == "W"))
        p.name, p.nation, p.rarity, p.body_type, p.weight_kg, p.height_cm = name, nation, rarity, body, 70.0, 178.0
        for k in ("agility", "balance", "dribbling", "ball_control"):
            p.attributes[k] = agi
        return p

    def test_lean_body_pays_more_on_an_agile_card(self):
        from fcrating.body import BodyCard
        bp = CFG["weights"]["body_profile"]
        slow, fast = self._card(agi=66), self._card(agi=92)
        b_slow = BodyCard(slow, "W", bp).points(slow.attributes, [], [])
        b_fast = BodyCard(fast, "W", bp).points(fast.attributes, [], [])
        self.assertGreater(b_fast - b_slow, 1.5)
        self.assertGreater(b_slow, 0.0)   # a good body is still worth something on a low card that can be evolved

    def test_reputation_counts_whatever_the_numbers(self):
        from fcrating.body import BodyCard
        bp = copy.deepcopy(CFG["weights"]["body_profile"])
        bp["reputation"] = {"points": {"Rykte Spiller": 2.0, "Kanu|FUT Heroes": -1.5}}
        good, plain = self._card(name="Rykte Spiller", agi=70), self._card(name="Annen", agi=70)
        hero, other = self._card(name="Kanu", rarity="FC 27 FUT Heroes"), self._card(name="Kanu", nation="Brazil")
        pts = lambda p: BodyCard(p, "W", bp).points(p.attributes, [], [])
        self.assertAlmostEqual(pts(good) - pts(plain), 2.0, places=6)
        self.assertAlmostEqual(pts(hero) - pts(other), -1.5, places=6)

    def test_unique_model_pays_only_on_an_agile_card(self):
        from fcrating.body import BodyCard
        bp = copy.deepcopy(CFG["weights"]["body_profile"])
        bp.pop("learned", None)
        pts = lambda p: BodyCard(p, "W", bp).points(p.attributes, [], [])
        for w in (66.0, 74.0):   # read as Lean Medium and as Average Medium at 178 cm
            fast_u, fast_s = self._card(name="U", body="Unik Spiller", agi=92), self._card(name="S", body="Lean Medium" if w < 70 else "Average Medium", agi=92)
            slow_u, slow_s = self._card(name="U", body="Unik Spiller", agi=66), self._card(name="S", body="Lean Medium" if w < 70 else "Average Medium", agi=66)
            for c in (fast_u, fast_s, slow_u, slow_s):
                c.weight_kg = w
            self.assertGreater(pts(fast_u) - pts(fast_s), 0.2)          # agile: the unique model gives a bonus
            self.assertAlmostEqual(pts(slow_u), pts(slow_s), places=6)  # slow: nothing for being unique


class ReputationSpreadTests(unittest.TestCase):
    """A known standard body shares part of its reputation with cards that have the same body type and about the
    same height and weight (more the more agile they are); a unique model is not shared."""

    def _p(self, name, body="Average Short", h=170.0, w=65.0, agi=88):
        import copy as _c
        p = _c.deepcopy(next(q for q in BASE if position_group(q.position) == "W"))
        p.name, p.nation, p.rarity, p.body_type, p.height_cm, p.weight_kg, p.gender = name, "X", "FC 27 Rare Gold", body, h, w, "M"
        for k in ("agility", "balance", "dribbling", "ball_control"):
            p.attributes[k] = agi
        return p

    def test_look_alike_bodies_share_the_reputation(self):
        from fcrating.body import BodyCard, attach_rep_frames
        bp = copy.deepcopy(CFG["weights"]["body_profile"])
        bp.pop("learned", None)
        bp["reputation"] = {"points": {"Kjent": 1.5}, "spread": {"share": 0.5, "height_cm": 4, "weight_kg": 6, "no_weight": 0.5}}
        known = self._p("Kjent")
        attach_rep_frames(bp, [known])
        pts = lambda p: BodyCard(p, "W", bp).points(p.attributes, [], [])
        base = pts(self._p("Ingen", h=190.0, w=85.0, body="Average Short"))   # same label, far off in size: nothing
        twin, near, slow = self._p("Tvilling"), self._p("Nær", h=172.0, w=68.0), self._p("Treg", agi=66)
        plain = copy.deepcopy(bp); plain["rep_frames"] = []
        ref = lambda p: BodyCard(p, "W", plain).points(p.attributes, [], [])
        self.assertGreater(pts(twin) - ref(twin), 0.5)                      # same body, agile: a clear share
        self.assertGreater(pts(twin) - ref(twin), pts(near) - ref(near))    # further off in size: less
        self.assertLess(pts(slow) - ref(slow), 0.05)                        # a slow card gets (almost) nothing
        self.assertAlmostEqual(base - ref(self._p("Ingen", h=190.0, w=85.0)), 0.0, places=6)
        uniq = self._p("Unik", body="Unik Modell")
        bp2 = copy.deepcopy(bp); bp2["reputation"]["points"] = {"Unik": 2.0}
        attach_rep_frames(bp2, [uniq])
        self.assertEqual(bp2["rep_frames"], [])                             # a unique model is not shared
