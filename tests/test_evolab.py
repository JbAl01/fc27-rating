"""Evo Lab: evo rules, live plan, simulations, cache, page and evo import."""
import copy
import json
import random
import sys
import tempfile
import unittest
from unittest import mock
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating import evo_import, evolab, evolab_report  # noqa: E402
from fcrating.model import load_config, rank_by_position, rate  # noqa: E402
from fcrating.schema import position_group  # noqa: E402
from fcrating.sources import local  # noqa: E402

CFG = load_config()
LAB = evolab.load_lab_config()
RULES = LAB["rules"]
BASE = local.load_json(str(ROOT / "data" / "eksempel_spillere.json"))


def card(name_part):
    return copy.deepcopy(next(p for p in BASE if name_part in p.name))


def low_striker(i=0, ovr=72, pace=(80, 82), ps=("Rapid",)):
    """A low-rated striker built from Ekitiké with weaker numbers."""
    p = card("Ekitiké")
    p.name, p.id, p.rarity, p.status = f"Test Spiss {i}", str(9000 + i), "Rare", ""
    p.ovr, p.alt_positions = ovr, []
    p.attributes = {k: max(40, v - 12) for k, v in p.attributes.items()}
    p.attributes["acceleration"], p.attributes["sprint_speed"] = pace
    p.playstyles, p.playstyles_plus, p.playstyles_complete = list(ps), [], True
    return p


def evo(key, req=None, up=None, **kw):
    return evolab.parse_evo(dict({"key": key, "name": key, "req": req or {}, "up": up or {}}, **kw))


class RuleTests(unittest.TestCase):
    def test_playstyle_cap_counts_what_the_card_has(self):
        st = evolab.state_from(low_striker(ps=("Rapid", "Technical")))
        st.ps, st.psp = ["Rapid", "Technical"], []
        e = evo("cap3", up={"ps": [["Gamechanger", 3]]})
        self.assertIn("Gamechanger", evolab.apply(e, st, RULES).ps)        # 2 PlayStyles -> gets the third
        st.ps = ["Rapid", "Technical", "Trickster"]
        self.assertNotIn("Gamechanger", evolab.apply(e, st, RULES).ps)     # already 3 -> nothing added

    def test_option_comes_after_the_shared_levels(self):
        st = evolab.state_from(low_striker())
        st.attrs["reactions"] = 70.0
        e = evo("fsa2", up={"stats": {"reactions": [2, 82]},
                             "paths": [{"label": "B", "stats": {"reactions": [1, 83]}, "wf": [2, 4]}]})
        st.wf = 2
        after = evolab.apply(e, st, RULES, e["up"]["paths"][0])
        self.assertEqual(after.attrs["reactions"], 73.0)   # +2 then +1, each up to its own max
        self.assertEqual(after.wf, 4)                      # options can raise weak foot too

    def test_two_roles_in_one_position(self):
        e = evo("mgu", up={"roles": [["CDM", "Deep-Lying Playmaker", 1], ["CDM", "Box Crasher", 1]]})
        st = evolab.state_from(low_striker())
        roles = evolab.apply(e, st, RULES).roles["CDM"]
        self.assertEqual(roles, {"Deep-Lying Playmaker": 1, "Box Crasher": 1})

    def test_upgrade_never_lowers_and_stops_at_cap(self):
        st = evolab.state_from(low_striker())
        st.attrs["finishing"], st.attrs["volleys"] = 70.0, 90.0
        e = evo("a", up={"stats": {"finishing": [7, 75], "volleys": [7, 80]}, "ovr": [40, 79]})
        out = evolab.apply(e, st, RULES)
        self.assertEqual(out.attrs["finishing"], 75)  # +7 would be 77, cap 75
        self.assertEqual(out.attrs["volleys"], 90)    # already above the cap: unchanged
        self.assertEqual(out.ovr, 79)                 # +40 = fill up to the cap
        self.assertEqual(st.attrs["finishing"], 70)   # the original is untouched

    def test_face_upgrade_raises_all_its_attributes(self):
        st = evolab.state_from(low_striker(pace=(80, 80)))
        out = evolab.apply(evo("f", up={"face": {"pace": [2, 84]}}), st, RULES)
        self.assertEqual((out.attrs["acceleration"], out.attrs["sprint_speed"]), (82, 82))
        st2 = evolab.state_from(low_striker(pace=(84, 84)))
        self.assertEqual(evolab.apply(evo("f", up={"face": {"pace": [2, 84]}}), st2, RULES).attrs["acceleration"], 84)

    def test_playstyle_plus_cap_is_three(self):
        st = evolab.state_from(low_striker(ps=("Rapid", "Technical")))
        st.psp = ["Finesse Shot", "Power Shot", "First Touch"]
        out = evolab.apply(evo("p", up={"psp": ["Rapid"]}), st, RULES)
        self.assertNotIn("Rapid", out.psp)  # FC 27: max 3 PlayStyle+
        st.psp = ["Finesse Shot"]
        out = evolab.apply(evo("p", up={"psp": ["Rapid"]}), st, RULES)
        self.assertIn("Rapid", out.psp)
        self.assertNotIn("Rapid", out.ps)  # upgraded from PlayStyle to PlayStyle+

    def test_requirements(self):
        st = evolab.state_from(low_striker(ovr=80, pace=(86, 86)))
        self.assertEqual(evolab.check(evo("x", {"max_ovr": 79}), st, RULES)[0], "ovr")
        self.assertEqual(evolab.check(evo("x", {"max_pace": 85}), st, RULES)[0], "pace")
        self.assertEqual(evolab.check(evo("x", {"positions": ["CB"]}), st, RULES)[0], "pos")
        st.positions = ("ST", "CAM")
        self.assertEqual(evolab.check(evo("x", {"positions": ["ST"], "not_positions": ["CAM"]}), st, RULES)[0], "pos")
        self.assertEqual(evolab.check(evo("x", {"max_ps": 0}), st, RULES)[0], "ps")
        self.assertIsNone(evolab.check(evo("x", {"max_ovr": 80, "max_pace": 86}), st, RULES))
        self.assertEqual(evolab.check(evo("x", {"requires_evo": "y"}), st, RULES)[0], "pre")

    def test_fast_rater_matches_rate(self):
        rng = random.Random(4)
        players = [copy.deepcopy(p) for p in BASE] + [low_striker(i, ovr=60 + i) for i in range(8)]
        uni = evolab.generate_universe(LAB, 1)
        n = 0
        for p in players:
            g = position_group(p.position)
            ev = evolab.Evaluator(p, g, CFG, RULES)
            st = evolab.state_from(p)
            for wave in uni:
                for e in wave:
                    if evolab.check(e, st, RULES) is None:
                        st = evolab.apply(e, st, RULES, rng.choice(e["up"]["paths"]) if e["up"]["paths"] else None)
                        full = rate(evolab.to_player(p, st, RULES, CFG), CFG, groups=[g])["by_group"].get(g, {}).get("igr", 0.0)
                        self.assertAlmostEqual(ev.fast.igr(st), full, places=6, msg=p.name)
                        n += 1
        self.assertGreater(n, 20)

    def test_inplace_simulation_matches_apply(self):
        uni = evolab.generate_universe(LAB, 2)
        for i in range(6):
            st = evolab.state_from(low_striker(i, ovr=62 + 3 * i))
            for evos, _ in evolab.card_waves({2: uni}, 2, st.positions):
                for e in evos:
                    if evolab._check_dyn(e, st, RULES) is None:
                        path = e["up"]["paths"][0] if e["up"]["paths"] else None
                        b = st.copy()
                        evolab._apply_inplace(e, b, RULES, path)
                        st = evolab.apply(e, st, RULES, path)
                        self.assertEqual(st.key(), b.key())

    def test_universes_are_deterministic(self):
        a = evolab.generate_universe(LAB, 3)
        b = evolab.generate_universe(LAB, 3)
        self.assertEqual([[e["key"] for e in w] for w in a], [[e["key"] for e in w] for w in b])
        self.assertEqual(a[0][0]["up"], b[0][0]["up"])


class PlanTests(unittest.TestCase):
    def plan(self, p, evos):
        g = position_group(p.position)
        ev = evolab.Evaluator(p, g, CFG, RULES)
        return evolab.plan_live(p, evolab.state_from(p), evos, ev, RULES)

    def test_restrictive_evo_first(self):
        p = low_striker(ovr=78)
        a = evo("A", {"max_ovr": 78, "positions": ["ST"]}, {"ovr": [2, 80], "stats": {"finishing": [6, 85]}})
        b = evo("B", {"max_ovr": 80, "positions": ["ST"]}, {"ovr": [2, 82], "stats": {"positioning": [6, 85]}})
        plan = self.plan(p, [b, a])
        self.assertEqual([s["key"] for s in plan["steps"]], ["A", "B"])
        self.assertTrue(any(t.startswith("A før B") for t in plan["tips"]))
        self.assertEqual(plan["ovr"], 82)

    def test_pace_trap(self):
        # B raises the pace above A's limit, so A must come first
        p = low_striker(ovr=74, pace=(80, 80))
        a = evo("A", {"max_ovr": 79, "max_pace": 81, "positions": ["ST"]}, {"ovr": [3, 79], "stats": {"finishing": [8, 85]}})
        b = evo("B", {"max_ovr": 79, "positions": ["ST"]}, {"stats": {"acceleration": [6, 90], "sprint_speed": [6, 90]}})
        plan = self.plan(p, [b, a])
        self.assertEqual([s["key"] for s in plan["steps"]], ["A", "B"])
        self.assertIn("farten", plan["tips"][0])

    def test_near_misses_and_unchecked(self):
        p = low_striker(ovr=76)
        near = evo("N", {"max_ovr": 75, "positions": ["ST"]}, {"ovr": [3, 79]})
        far = evo("F", {"max_ovr": 70, "positions": ["ST"]}, {"ovr": [3, 79]})
        age = evo("Y", {"max_ovr": 80, "positions": ["ST"]}, {"ovr": [3, 80]}, unchecked="født etter 2003")
        plan = self.plan(p, [near, far, age])
        self.assertEqual([n[0] for n in plan["near"]], ["N"])  # 1 over the limit, the 6-over one is not "nesten"
        self.assertEqual(plan["chk"], [["Y", "født etter 2003"]])
        self.assertEqual(plan["steps"], [])

    def test_age_requirement_uses_birthdate(self):
        req = {"max_ovr": 80, "positions": ["ST"], "born_from": "2003-10-09"}
        y = evo("Y", req, {"ovr": [3, 80], "stats": {"finishing": [8, 90]}})
        young = low_striker(ovr=76)
        young.birthdate = "2005-02-01"
        plan = self.plan(young, [y])
        self.assertEqual([s["key"] for s in plan["steps"]], ["Y"])
        old = low_striker(ovr=76)
        old.birthdate = "2001-05-05"
        plan = self.plan(old, [y])
        self.assertEqual(plan["steps"], [])
        self.assertEqual(plan["chk"], [])
        why = evolab.check(y, evolab.state_from(old), RULES)
        self.assertEqual(why[0], "age")
        self.assertIn("9. oktober 2003", why[1])
        unknown = low_striker(ovr=76)          # no date of birth: «sjekk selv», not in the plan
        plan = self.plan(unknown, [y])
        self.assertEqual(plan["steps"], [])
        self.assertEqual(plan["chk"][0][0], "Y")
        self.assertIn("fødselsdato mangler", plan["chk"][0][1])
        # the next evo in the chain follows
        y2 = evo("Y2", {"min_ovr": 79, "requires_evo": "Y"}, {"ovr": [1, 81]})
        plan = self.plan(unknown, [y, y2])
        self.assertEqual([c[0] for c in plan["chk"]], ["Y", "Y2"])

    def test_pathway_choice(self):
        p = low_striker(ovr=74, ps=())
        e = evo("P", {"max_ovr": 79}, {"paths": [{"label": "Jockey", "ps": ["Jockey"]}, {"label": "Finesse Shot", "ps": ["Finesse Shot"]}]})
        plan = self.plan(p, [e])
        self.assertEqual(plan["steps"][0]["path"], "Finesse Shot")  # the striker wants the shooting PlayStyle

    def test_active_live_respects_dates_and_own_file(self):
        with tempfile.TemporaryDirectory() as d:
            own = Path(d) / "mine.json"
            own.write_text('{"evos": [{"key": "batigol_precision", "name": "Min Batigol", "req": {"max_ovr": 90}, "up": {}}]}',
                           encoding="utf-8")
            live, expired = evolab.active_live(LAB, date(2026, 10, 16), own)
            names = {e["name"] for e in live}
            self.assertIn("Min Batigol", names)            # your own file wins over the config
            self.assertNotIn("Goal Guardian", names)       # could be started until 15 Oct 17:00 UTC
            self.assertIn("Goal Guardian", expired)
            live2, _ = evolab.active_live(LAB, date(2026, 10, 15), Path(d) / "none.json")
            self.assertIn("Goal Guardian", {e["name"] for e in live2})
            none = Path(d) / "none.json"
            just_before = datetime(2026, 10, 15, 16, 59, tzinfo=timezone.utc)
            at_close = datetime(2026, 10, 15, 17, 0, tzinfo=timezone.utc)
            self.assertIn("Goal Guardian", {e["name"] for e in evolab.active_live(LAB, user_file=none, now=just_before)[0]})
            self.assertIn("Goal Guardian", evolab.active_live(LAB, user_file=none, now=at_close)[1])

    def test_live_evos_have_sources_and_close_times(self):
        for raw in LAB["live"]:
            self.assertTrue(raw.get("sources"), raw["key"])
            self.assertIsNotNone(evolab.until_utc(raw["until"]), raw["key"])
        self.assertEqual(evolab.until_utc("2026-10-17").hour, 17)  # a plain date means 18:00 in the UK


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.players = [copy.deepcopy(p) for p in BASE] + [low_striker(i, ovr=58 + 2 * i) for i in range(10)]
        cls.results = [rate(p, CFG) for p in cls.players]
        rank_by_position(cls.results, CFG)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cache = Path(cls.tmp.name) / "cache.pkl"
        cls.lab_run = evolab.run(cls.players, cls.results, CFG, cache_path=cls.cache, today=date(2026, 10, 11), quiet=True,
                             user_file=Path(cls.tmp.name) / "none.json", used_file=Path(cls.tmp.name) / "none_used.json")
        cls.summary = evolab.summarize(cls.lab_run, cls.players, cls.results, CFG)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_eligibility(self):
        names = {r["name"]: r["uid"] for r in self.results}
        self.assertNotIn(names["Kylian Mbappé"], self.summary)       # 91 OVR: too high
        self.assertNotIn(names["Yuki Nagasato"], self.summary)       # Icon
        self.assertIn(names["Test Spiss 0"], self.summary)

    def test_forecast_without_todays_evos(self):
        """Cards with a live plan also get the forecast from today's card (z), so the page can adjust the
        forecast when evos are marked as used. Cards without a live plan do not need it."""
        with_plan = [s for s in self.summary.values() if s["live"]["steps"]]
        self.assertTrue(with_plan)
        for s in with_plan:
            for h in s["h"][1:]:
                p10, p50, p90, op, ovr = h["z"]
                self.assertLessEqual(p10, p50 + 1e-9)
                self.assertLessEqual(p50, p90 + 1e-9)
                self.assertTrue(0 <= op <= 100)
            self.assertNotIn("z", s["h"][0])
        for s in self.summary.values():
            if not s["live"]["steps"]:
                self.assertTrue(all("z" not in h for h in s["h"]))

    def test_summary_numbers(self):
        hz = evolab.horizons(LAB)
        for uid, s in self.summary.items():
            self.assertEqual(len(s["h"]), len(hz))
            for h in s["h"]:
                self.assertLessEqual(h["p10"], h["p50"] + 1e-9)
                self.assertLessEqual(h["p50"], h["p90"] + 1e-9)
                self.assertTrue(0 <= h["op"] <= 100)
            self.assertGreaterEqual(s["h"][0]["p50"], s["now"] - 0.05)  # evos never make a card worse
            self.assertTrue(0 < s["dna"]["top"] <= 100)

    def test_low_cards_gain_most(self):
        low = [s for s in self.summary.values() if s["ovr"] and s["ovr"] <= 64]
        high = [s for s in self.summary.values() if s["ovr"] and s["ovr"] >= 80]
        self.assertGreater(min(x["gain"] for x in low), max(x["gain"] for x in high))

    def test_cache_is_reused(self):
        again = evolab.run(self.players, self.results, CFG, cache_path=self.cache, today=date(2026, 10, 11), quiet=True,
                           user_file=Path(self.tmp.name) / "none.json")
        for uid, e in self.lab_run["entries"].items():
            self.assertEqual(again["entries"][uid]["mc"], e["mc"])
        self.assertEqual(sum(e.get("calls", 0) for e in again["entries"].values()),
                         sum(e.get("calls", 0) for e in self.lab_run["entries"].values()))  # nothing simulated again

    def test_used_evos_are_left_out(self):
        used = Path(self.tmp.name) / "brukt.json"
        evolab.save_used(["batigol_precision", "Nine Duty"], used)
        self.assertEqual(sorted(evolab.load_used(used)), ["batigol_precision", "nine duty"])
        run2 = evolab.run(self.players, self.results, CFG, cache_path=Path(self.tmp.name) / "c2.pkl", today=date(2026, 10, 11),
                          quiet=True, user_file=Path(self.tmp.name) / "none.json", used_file=used)
        names = {e["name"] for e in run2["live"]}
        self.assertNotIn("Batigol Precision", names)
        self.assertNotIn("Nine Duty", names)
        self.assertEqual(sorted(run2["used"]), ["Batigol Precision", "Nine Duty"])

    def test_update_evos_and_page(self):
        evos = {r["uid"]: {"eligible": False} for r in self.results}
        evolab.update_evos(evos, self.summary, LAB)
        uid = next(iter(self.summary))
        self.assertEqual(evos[uid]["igr_after"], self.summary[uid]["h"][0]["p50"])   # the evos that are out now
        page = evolab_report.render(self.summary, self.results, self.lab_run, CFG)
        self.assertIn("Evo Lab", page)
        self.assertIn("Test Spiss 0", page)
        self.assertNotIn("__DATA__", page)
        self.assertNotIn("__U__", page)
        with tempfile.TemporaryDirectory() as d:
            paths = evolab_report.write(self.summary, self.results, self.lab_run, CFG, d)
            self.assertTrue(Path(paths["csv"]).read_text(encoding="utf-8-sig").startswith("name;version"))


class ImportTests(unittest.TestCase):
    def test_futbin_style(self):
        text = """Batigol Precision
Requirements
Overall max 81
Pace max 85
Max PS 7
Positions: ST
Not: CB, CM, CAM
Upgrades
Overall +6 (max 83)
Finishing +7 (max 83)
Att. Position +7 (max 84)
Skill Moves +1 (max 3)
PlayStyle: Tiki Taka
"""
        e = evo_import.parse(text)
        self.assertEqual(e["name"], "Batigol Precision")
        self.assertEqual(e["req"]["max_ovr"], 81)
        self.assertEqual(e["req"]["max_pace"], 85)
        self.assertEqual(e["req"]["max_ps"], 7)
        self.assertEqual(e["req"]["positions"], ["ST"])
        self.assertEqual(e["req"]["not_positions"], ["CB", "CM", "CAM"])
        self.assertEqual(e["up"]["ovr"], [6, 83])
        self.assertEqual(e["up"]["stats"]["finishing"], [7, 83])
        self.assertEqual(e["up"]["stats"]["positioning"], [7, 84])
        self.assertEqual(e["up"]["sm"], [1, 3])
        self.assertEqual(e["up"]["ps"], ["Tiki Taka"])

    def test_futgg_style_split_lines(self):
        text = """Nine Duty
Overall
Max. 74
Pace
Max. 85
Max PS
7
+40
OVR
79
+50
Positioning
80
+40
Ball Control
78
+2
SM3
Gamechanger 3
Finesse Shot 4
"""
        e = evo_import.parse(text)
        self.assertEqual(e["req"]["max_ovr"], 74)
        self.assertEqual(e["req"]["max_pace"], 85)
        self.assertEqual(e["up"]["ovr"], [40, 79])
        self.assertEqual(e["up"]["stats"]["positioning"], [50, 80])
        self.assertEqual(e["up"]["stats"]["ball_control"], [40, 78])
        self.assertEqual(e["up"]["sm"], [2, 3])
        # the number after a PlayStyle is EA's cap, not a PlayStyle+ marker
        self.assertIn(["Gamechanger", 3], e["up"]["ps"])
        self.assertIn(["Finesse Shot", 4], e["up"]["ps"])
        self.assertNotIn("psp", e["up"])
        e2 = evo_import.parse("Test\nOverall max 80\nPlayStyle+ Finesse Shot+")
        self.assertEqual(e2["up"]["psp"], ["Finesse Shot"])
        parsed = evolab.parse_evo(dict(e, key="x"))
        self.assertIn(("Gamechanger", 3), parsed["up"]["ps"])

    def test_face_stats_and_save(self):
        e = evo_import.parse("Frontline Flair\nOverall max 83\nPace max 84\nPace +2 (max 84)\nDribbling +2 (max 84)\nOverall +1 (max 84)")
        self.assertEqual(e["up"]["face"]["pace"], [2, 84])
        self.assertEqual(e["up"]["face"]["dribbling"], [2, 84])  # with other main stats, Dribbling is the main stat
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "mine.json"
            self.assertEqual(evo_import.save(e, path, until="2026-10-18"), 1)
            self.assertEqual(evo_import.save(e, path), 1)  # same key replaces
            live, _ = evolab.active_live(LAB, date(2026, 10, 12), path)
            self.assertIn("Frontline Flair", [x["name"] for x in live])


if __name__ == "__main__":
    unittest.main()


class PageMathTests(unittest.TestCase):
    """The page carries the same maths as Python; check the inputs it gets and the Python side of it."""

    def test_detail_matches_rate_and_runs(self):
        from fcrating import runs
        rc = CFG["weights"]["run_ai"]
        w = dict(evolab._clean(rc["weights"]))
        for p in [copy.deepcopy(x) for x in BASE] + [low_striker(i, ovr=60 + 2 * i) for i in range(6)]:
            g = position_group(p.position)
            st = evolab.state_from(p)
            d = evolab.FastRater(p, g, CFG).detail(st)
            r = rate(evolab.to_player(p, st, RULES, CFG), CFG, groups=[g])
            vil, eff = runs.sub_scores(runs.features(st.attrs, p.work_rate_att, rc, p.height_cm), w, rc)
            self.assertEqual(d["igr"], r["by_group"][g]["igr"])
            self.assertEqual(d["feel"], r["feel"])
            self.assertEqual(d["acc"], r["accelerate"])
            self.assertEqual((d["vil"], d["eff"]), (vil, eff))
            self.assertEqual(d["run"], runs.card_run_score(st.attrs, p.work_rate_att, p.height_cm, CFG))

    def test_page_payload(self):
        import json as _json
        players = [copy.deepcopy(p) for p in BASE] + [low_striker(i, ovr=58 + 2 * i) for i in range(10)]
        results = [rate(p, CFG) for p in players]
        rank_by_position(results, CFG)
        with tempfile.TemporaryDirectory() as d:
            run = evolab.run(players, results, CFG, cache_path=Path(d) / "c.pkl", today=date(2026, 10, 11), quiet=True,
                             user_file=Path(d) / "none.json")
            summ = evolab.summarize(run, players, results, CFG)
            page = evolab_report.render(summ, results, run, CFG, players)
        meta = _json.loads(page[page.index(",META=") + 6:page.index(",STR=")])
        rows = _json.loads(page[page.index("const RAW=") + 10:page.index(",META=")])
        self.assertEqual(len(rows), len(summ))
        self.assertIn("ST", meta["rate"]["G"])
        self.assertTrue(meta["evos"])
        for r in rows:
            self.assertEqual(len(r), 41)
            for ei, pi in r[19][0][0]:  # the plan points at live evos and their pathways
                self.assertLess(ei, len(meta["evos"]))
                self.assertLess(pi, max(1, len(meta["evos"][ei][8][8])))
        st0 = next(s for s in summ.values() if s.get("runcard"))
        self.assertEqual(len(st0["runs"]["end"]), 3)
        self.assertEqual(len(st0["cats"]["end"]), len(meta["cats"]))


    def test_twin_targets_cover_every_outfield_position(self):
        """«Ligner på» can be any outfield card with the movement data, not only forwards; never a keeper."""
        players = [copy.deepcopy(p) for p in BASE]
        cb = card("Meza")
        cb.name, cb.id, cb.position, cb.alt_positions, cb.ovr, cb.height_cm = "Test Midtstopper", "777", "CB", [], 90, 188.0
        gk = card("Haaland")
        gk.name, gk.id, gk.position, gk.alt_positions, gk.ovr = "Test Keeper", "778", "GK", [], 90
        players += [cb, gk]
        results = [rate(p, CFG) for p in players]
        rank_by_position(results, CFG)
        tg, sim = evolab_report.targets_meta(results, LAB, CFG)
        names = {t[0] for t in tg}
        self.assertIn("Test Midtstopper", names)
        self.assertNotIn("Test Keeper", names)
        self.assertTrue(all(len(t[3]) == len(sim["keys"]) for t in tg))


class AutoEvoFileTests(unittest.TestCase):
    """data/auto_evoer.json (daily check) is read next to your own file, and evo-sjekk catches mistakes."""

    def evo(self, **kw):
        d = {"key": "x", "name": "X", "cost": "gratis", "until": "2026-12-01T17:00Z", "req": {"max_ovr": 80},
             "up": {"ovr": [3, 80], "stats": {"finishing": [3, 80]}},
             "sources": ["https://a.example/x", "https://b.example/x"]}
        d.update(kw)
        return d

    def test_valid_evo_has_no_problems(self):
        self.assertEqual(evolab.check_evo(self.evo(), min_sources=2), [])

    def test_unknown_deadline_allowed_only_with_flag_and_note(self):
        ok = self.evo(until=None, until_ukjent=True, note="Frist ukjent i kildene.")
        self.assertEqual(evolab.check_evo(ok, min_sources=2), [])
        self.assertTrue(evolab.check_evo(self.evo(until=None, until_ukjent=True), min_sources=2))
        self.assertTrue(evolab.check_evo(self.evo(until=None), min_sources=2))

    def test_catches_common_mistakes(self):
        cases = [
            (self.evo(until=None), "until"),
            (self.evo(until="i morgen"), "until"),
            (self.evo(sources=["https://a.example/x"]), "kilde"),
            (self.evo(up={"stats": {"finishin": [3, 80]}}), "ukjent attributt"),
            (self.evo(up={"stats": {"finishing": [3, 180]}}), "økning"),
            (self.evo(up={"ps": ["Rapidd"]}), "ukjent PlayStyle"),
            (self.evo(req={"positions": ["XX"]}), "posisjon"),
            (self.evo(req={"min_ovr": 82, "max_ovr": 80}), "min_ovr"),
            (self.evo(req={"born_from": "9. okt 2003"}), "born_from"),
            (self.evo(up={"paths": [{"ovr": [1, 83]}]}), "label"),
            ({"name": "X"}, "key"),
        ]
        names = {"Rapid", "Technical"}
        for evo, word in cases:
            probs = evolab.check_evo(evo, min_sources=2, playstyles=names)
            self.assertTrue(any(word in p for p in probs), (word, probs))

    def test_auto_file_is_loaded_and_own_file_wins(self):
        with tempfile.TemporaryDirectory() as d:
            auto, mine = Path(d) / "auto.json", Path(d) / "mine.json"
            auto.write_text(json.dumps({"evos": [self.evo(key="a", name="Auto A"), self.evo(key="b", name="Auto B")]}))
            mine.write_text(json.dumps({"evos": [self.evo(key="b", name="Min B")]}))
            with mock.patch.object(evolab, "auto_evos_path", return_value=auto), \
                 mock.patch.object(evolab, "user_evos_path", return_value=mine):
                got = {e["key"]: (e["name"], e["source"]) for e in evolab.load_user_evos()}
                self.assertEqual(got, {"b": ("Min B", "egen"), "a": ("Auto A", "auto")})
                only = evolab.load_user_evos(auto)
                self.assertEqual({e["key"] for e in only}, {"a", "b"})

    def test_shipped_auto_file_is_valid(self):
        import json as _json
        p = evolab.auto_evos_path()
        if not p.exists():
            self.skipTest("ingen auto-fil")
        names = set(_json.load(open(evolab.ROOT / "config" / "playstyles.json", encoding="utf-8"))["playstyles"])
        for e in _json.load(open(p, encoding="utf-8"))["evos"]:
            self.assertEqual(evolab.check_evo(e, min_sources=2, playstyles=names), [], e["key"])


class PlanSearchTests(unittest.TestCase):
    """The live plan must find the best combination, also when an evo has to be skipped or taken later."""

    def plan(self, p, evos):
        g = evolab.card_group(p) or "ST"
        ev = evolab.Evaluator(p, g, CFG, RULES)
        return evolab.plan_live(p, evolab.state_from(p), evos, ev, RULES)

    def test_takes_the_small_ovr_evo_first_so_both_fit(self):
        p = low_striker(ovr=75)
        big_ovr = evo("big_ovr", {"max_ovr": 80}, {"ovr": [7, 90], "stats": {"finishing": [2, 99]}})
        small = evo("small", {"max_ovr": 81}, {"ovr": [1, 90], "stats": {"finishing": [12, 99], "positioning": [12, 99]}})
        steps = [s["key"] for s in self.plan(p, [big_ovr, small])["steps"]]
        self.assertEqual(sorted(steps), ["big_ovr", "small"])
        self.assertEqual(steps[0], "small")   # the other order shuts the card out of "small"

    def test_skips_an_evo_that_would_shut_out_a_better_one(self):
        p = low_striker(ovr=74)
        weak_lift = evo("weak_lift", {"max_ovr": 79}, {"ovr": [6, 90], "stats": {"stamina": [3, 99]}})
        strong = evo("strong", {"max_ovr": 75}, {"ovr": [1, 90], "stats": {"finishing": [15, 99], "reactions": [15, 99]}})
        blocker = evo("blocker", {"max_ovr": 74}, {"ovr": [8, 90], "stats": {"stamina": [2, 99]}})
        pl = self.plan(p, [weak_lift, strong, blocker])
        keys = [s["key"] for s in pl["steps"]]
        self.assertIn("strong", keys)
        self.assertNotIn("blocker", keys)     # taking it first would shut out "strong" and "weak_lift"

    def test_special_card_with_base_playstyles_is_not_planned_at_the_ps_limit(self):
        p = low_striker(ovr=74)
        p.playstyles = ["Rapid", "Finesse Shot"]
        tech = evo("tech", {"max_ps": 2}, {"ps": ["Technical"]})
        self.assertIn("tech", [s["key"] for s in self.plan(p, [tech])["steps"]])
        p.ps_from_base = True   # promo card: may have one PlayStyle more than the base card
        pl = self.plan(p, [tech])
        self.assertNotIn("tech", [s["key"] for s in pl["steps"]])
        self.assertTrue(any("PlayStyles" in c[1] for c in pl["chk"]))

    def test_search_never_worse_than_any_single_order(self):
        import itertools
        p = low_striker(ovr=72)
        evos = [evo("a", {"max_ovr": 78}, {"ovr": [4, 90], "stats": {"finishing": [6, 99]}}),
                evo("b", {"max_ovr": 74}, {"ovr": [3, 90], "stats": {"positioning": [8, 99]}}),
                evo("c", {"max_ovr": 80}, {"ovr": [2, 90], "stats": {"reactions": [5, 99]}}),
                evo("d", {"max_ps": 1}, {"ps": ["Technical"]})]
        g = evolab.card_group(p) or "ST"
        ev = evolab.Evaluator(p, g, CFG, RULES)
        best = self.plan(p, evos)["igr"]
        st0 = evolab.state_from(p)
        for order in itertools.permutations(evos):
            st = st0
            for e in order:
                if evolab.check(e, st, RULES) is None:
                    st = evolab.apply(e, st, RULES)
            fin, _ = evolab.roles_plus_plus(st, p.position)
            self.assertLessEqual(round(ev.fast.detail(fin)["igr"], 1), best + 1e-9)

    def test_plans_for_other_goals(self):
        p = low_striker(ovr=74)
        igr_evo = evo("igr_evo", {"max_ovr": 74}, {"ovr": [6, 90], "stats": {
            "finishing": [25, 99], "shot_power": [25, 99], "composure": [25, 99], "ball_control": [20, 99], "dribbling": [20, 99]}})
        run_evo = evo("run_evo", {"max_ovr": 74}, {"ovr": [1, 90], "stats": {"positioning": [10, 99], "sprint_speed": [8, 99]}})
        pl = self.plan(p, [igr_evo, run_evo])
        self.assertEqual([s["key"] for s in pl["steps"]], ["igr_evo"])
        alt = pl["alt"]
        self.assertIn("run", alt)
        self.assertEqual([k for k, _ in alt["run"]["seq"]], ["run_evo"])

class DefenderPlanTests(unittest.TestCase):
    """CB, backs and CDM: a plan for best Forsvar, and never an attacking PlayStyle such as Gamechanger."""

    def defender(self, pos="CB"):
        p = card("Meza")
        p.name, p.id, p.rarity, p.status, p.position, p.alt_positions, p.ovr = f"Test {pos}", "8800", "Rare", "", pos, [], 72
        p.playstyles, p.playstyles_plus, p.playstyles_complete = [], [], True
        return p

    def plan(self, p, evos):
        g = evolab.card_group(p)
        return evolab.plan_live(p, evolab.state_from(p), evos, evolab.Evaluator(p, g, CFG, RULES), RULES)

    def test_no_attacking_playstyle_for_a_centre_back(self):
        p = self.defender()
        choice = evo("choice", {"max_ovr": 80}, {"paths": [{"label": "Valg A: Gamechanger", "ps": [["Gamechanger", 4]]},
                                                           {"label": "Valg B: Inventive", "ps": [["Inventive", 4]]}]})
        only_gc = evo("only_gc", {"max_ovr": 80}, {"ps": ["Gamechanger"]})
        pl = self.plan(p, [choice, only_gc])
        self.assertEqual([[s["key"], s["path"]] for s in pl["steps"]], [["choice", "Valg B: Inventive"]])
        self.assertIn(["only_gc", "gir bare en angreps-PlayStyle, som ikke hjelper en forsvarer"], pl["skip"])
        st = pl["_state"]
        self.assertNotIn("Gamechanger", st.ps + st.psp)
        # a striker may still choose it
        self.assertEqual(evolab.plan_paths(choice, "ST", RULES), choice["up"]["paths"])
        self.assertEqual(evolab.plan_paths(only_gc, "CB", RULES), [])
        self.assertEqual(evolab.plan_paths(only_gc, "ST", RULES), [None])

    def test_forced_attacking_playstyle_is_kept_when_the_evo_gives_more(self):
        both = evo("both", {"max_ovr": 80}, {"ps": ["Gamechanger"], "stats": {"standing_tackle": [8, 99]}})
        self.assertEqual(evolab.plan_paths(both, "CB", RULES), [None])

    def test_plan_for_best_defence(self):
        p = self.defender()
        pace_evo = evo("pace_evo", {"max_ovr": 72}, {"ovr": [3, 90], "stats": {
            "acceleration": [25, 99], "sprint_speed": [25, 99], "short_passing": [20, 99], "composure": [20, 99]}})
        def_evo = evo("def_evo", {"max_ovr": 72}, {"ovr": [1, 90], "stats": {"def_awareness": [4, 99], "interceptions": [4, 99]}})
        pl = self.plan(p, [pace_evo, def_evo])   # both lift OVR past 72, so only one of them fits
        self.assertEqual([s["key"] for s in pl["steps"]], ["pace_evo"])
        self.assertEqual([k for k, _ in pl["alt"]["def"]["seq"]], ["def_evo"])
        self.assertGreater(pl["alt"]["def"]["def"], pl["def"])
        self.assertIsNone(evolab.def_value(p.attributes, "ST", RULES))
