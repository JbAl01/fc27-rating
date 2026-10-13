import copy
import unittest

from fcrating import stop
from fcrating.evolab import FastRater, state_from
from fcrating.model import load_config, rate
from fcrating.schema import Player

CFG = load_config()
BASE = {"acceleration": 85, "sprint_speed": 85, "strength": 80, "balance": 80, "ball_control": 84, "dribbling": 84,
        "agility": 82, "reactions": 82, "stamina": 80, "positioning": 85, "finishing": 84, "shot_power": 80,
        "composure": 80, "vision": 70, "short_passing": 75, "long_shots": 75, "volleys": 75, "heading_accuracy": 70,
        "jumping": 70, "aggression": 60, "interceptions": 40, "defensive_awareness": 35, "standing_tackle": 35,
        "sliding_tackle": 30, "crossing": 70, "curve": 70, "long_passing": 65, "fk_accuracy": 60, "penalties": 70}


def player(**kw):
    attrs = dict(BASE)
    attrs.update(kw.pop("attrs", {}))
    data = {"name": kw.pop("name", "Test"), "position": "ST", "ovr": 85, "height_cm": kw.pop("h", 180),
            "attributes": attrs, **kw}
    return Player.from_dict(data)


class StopTests(unittest.TestCase):
    def test_fast_and_strong_is_hardest_to_stop(self):
        a = stop.scores(player().attributes, "Controlled", [], [], CFG)
        weak = stop.scores(player(attrs={"strength": 55, "balance": 60}).attributes, "Controlled", [], [], CFG)
        slow = stop.scores(player(attrs={"sprint_speed": 65, "acceleration": 65}).attributes, "Controlled", [], [], CFG)
        self.assertGreater(a[0], weak[0])
        self.assertGreater(a[0], slow[0])
        # both parts move: less strength costs on the run, less speed costs with the ball
        self.assertGreater(a[2], weak[2])
        self.assertGreater(a[1], slow[1])

    def test_lengthy_helps_on_a_run_only(self):
        c = stop.scores(BASE, "Controlled", [], [], CFG)
        le = stop.scores(BASE, "Lengthy", [], [], CFG)
        self.assertEqual(c[1], le[1])
        self.assertGreater(le[2], c[2])

    def test_playstyles_add_with_cap(self):
        none = stop.scores(BASE, None, [], [], CFG)
        rapid = stop.scores(BASE, None, [], ["Rapid"], CFG)
        many = stop.scores(BASE, None, [], ["Rapid", "Press Proven", "Enforcer", "Technical", "Bruiser"], CFG)
        cap = CFG["weights"]["hard_to_stop"]["ps_cap_ball"]
        self.assertAlmostEqual(rapid[1] - none[1], 3.0, places=6)
        self.assertAlmostEqual(many[1] - none[1], cap, places=6)

    def test_rate_and_fast_rater_agree_with_playstyles(self):
        for ps, psp, h in (([], [], 180), (["Rapid", "Bruiser"], ["Press Proven"], 190), (["Quick Step"], ["Rapid"], 168)):
            p = player(playstyles=ps, playstyles_plus=psp, h=h, attrs={"strength": 86, "agility": 70})
            r = rate(p, CFG, groups=["ST", "W", "CAM"])
            for g in ("ST", "W", "CAM"):
                fr = FastRater(p, g, CFG)
                d = fr.detail(state_from(p))
                self.assertEqual(d["igr"], r["by_group"][g]["igr"], (ps, psp, g))
                self.assertEqual(d["stp"], r["hard_to_stop"]["score"])
                self.assertEqual((d["stb"], d["stl"]), (r["hard_to_stop"]["ball"], r["hard_to_stop"]["run"]))

    def test_goalkeepers_have_none(self):
        p = player(position="GK")
        self.assertIsNone(rate(p, CFG)["hard_to_stop"])

    def test_old_config_without_section(self):
        cfg = copy.deepcopy(CFG)
        del cfg["weights"]["hard_to_stop"]
        self.assertEqual(stop.scores(BASE, None, [], [], cfg), (None, None, None))
        self.assertIsNone(rate(player(), cfg)["hard_to_stop"])


if __name__ == "__main__":
    unittest.main()
