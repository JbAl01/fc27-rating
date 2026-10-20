"""Run with:  python -m unittest discover -s tests"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating import accelerate as acc  # noqa: E402
from fcrating.explain import why_lines  # noqa: E402
from fcrating.model import (apply_chem, evo_boost, evo_potential, evolved_copy, load_config,  # noqa: E402
                            playstyle_bonus, rank_by_position, rank_evos, rate, weighted)
from fcrating.report import render_html, flat_row  # noqa: E402
from fcrating.schema import Player  # noqa: E402
from fcrating.sources import local  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
CFG = load_config()
RULES = CFG["weights"]["accelerate_rules"]
PLAYERS = {p.name.split()[1] if " " in p.name else p.name: p
           for p in local.load_json(str(ROOT / "data" / "eksempel_spillere.json"))}


def player(key):
    return copy.deepcopy(PLAYERS[key])


class AccelerateTests(unittest.TestCase):
    def test_known_cards_match_the_game(self):
        # AcceleRATE shown by FUT.GG / FUTBIN / your EasySBC screenshot
        for key, expected in [("Mbappé", "Explosive"), ("Haaland", "Lengthy"),
                              ("Ekitiké", "Controlled"), ("Nagasato", "Controlled")]:
            p = player(key)
            got, _ = acc.classify(p.attributes, p.height_cm, p.gender, RULES)
            self.assertEqual(got, expected, key)

    def test_strength_boost_flips_mbappe_to_controlled(self):
        # FUT.GG shows Mbappé turning Controlled with physical chem styles
        p = player("Mbappé")
        attrs = dict(p.attributes, strength=p.attributes["strength"] + 6)
        self.assertEqual(acc.classify(attrs, p.height_cm, "M", RULES)[0], "Controlled")

    def test_strength_boost_flips_ekitike_to_lengthy(self):
        # FUT.GG shows Ekitiké turning Lengthy with physical chem styles
        p = player("Ekitiké")
        attrs = dict(p.attributes, strength=p.attributes["strength"] + 4)
        self.assertEqual(acc.classify(attrs, p.height_cm, "M", RULES)[0], "Lengthy")

    def test_nagasato_finisher_only_blocked_by_height(self):
        p = player("Nagasato")
        boosted = apply_chem(p.attributes, "Finisher", CFG["chem"])
        self.assertEqual(acc.classify(boosted, 164, "F", RULES)[0], "Controlled")
        self.assertEqual(acc.classify(boosted, 162, "F", RULES)[0], "Explosive")

    def test_missing_height(self):
        p = player("Meza")
        self.assertIsNone(acc.classify(p.attributes, None, "M", RULES)[0])
        slow = dict(p.attributes, acceleration=60)
        self.assertEqual(acc.classify(slow, None, "M", RULES)[0], "Controlled")

    def test_female_lengthy_threshold(self):
        attrs = {"agility": 60, "strength": 80, "acceleration": 70}
        self.assertEqual(acc.classify(attrs, 172, "F", RULES)[0], "Lengthy")
        self.assertEqual(acc.classify(attrs, 171, "F", RULES)[0], "Controlled")


class ChemTests(unittest.TestCase):
    def test_finisher_reproduces_screenshot(self):
        boosted = apply_chem(player("Nagasato").attributes, "Finisher", CFG["chem"])
        screenshot = {"positioning": 96, "finishing": 99, "shot_power": 88, "volleys": 92, "penalties": 88,
                      "agility": 96, "balance": 86, "reactions": 93, "dribbling": 96, "ball_control": 92}
        for k, v in screenshot.items():
            self.assertEqual(boosted[k], v, k)

    def test_off_balance_estimate_matches_screenshot(self):
        p = player("Nagasato")
        w = CFG["weights"]["off_balance_dribbling"]["weights"]
        # EasySBC shows whole numbers: 87 for the card and 93 with Finisher (the average of Agility, Balance, Dribbling)
        self.assertEqual(round(acc.off_balance_dribbling(apply_chem(p.attributes, "Finisher", CFG["chem"]), w)), 93)
        self.assertEqual(round(acc.off_balance_dribbling(p.attributes, w)), 87)
        self.assertEqual(acc.off_balance_dribbling({"agility": 90, "balance": 80, "dribbling": 70}, w), 80.0)

    def test_chem_levels(self):
        attrs = {"finishing": 50, "positioning": 50, "shot_power": 50}
        two = apply_chem(attrs, "Finisher", CFG["chem"], level=2)
        one = apply_chem(attrs, "Finisher", CFG["chem"], level=1)
        self.assertEqual((two["finishing"], two["positioning"], two["shot_power"]), (56, 54, 52))
        self.assertEqual((one["finishing"], one["positioning"], one["shot_power"]), (53, 52, 51))

    def test_cap_99(self):
        self.assertEqual(apply_chem({"finishing": 95}, "Finisher", CFG["chem"])["finishing"], 99)


class ModelTests(unittest.TestCase):
    def test_feel_order_matches_in_game_experience(self):
        """Følelse med ball (the feel score + the body, as on the pages) with the cards' real body types: Mbappé's
        body is what puts him first (owner: his body is something else); Nagasato (164 cm) feels quicker than Messi
        (169 cm) because real height drives the animations in FC 27. Acceleration and AcceleRATE are in pace, not
        here (20.10, no double counting)."""
        bodies = {"Mbappé": ("Kylian Mbappé", 81), "Messi": ("Lionel Messi", 67), "Nagasato": ("Average Short", 58),
                  "Ekitiké": ("Lean Tall", 76), "Haaland": ("Erling Haaland", 88)}
        feel = {}
        for k, (bt, w) in bodies.items():
            p = player(k)
            p.body_type, p.weight_kg = bt, w
            r = rate(p, CFG)
            feel[k] = r["feel"] + r["by_group"]["ST" if "ST" in r["by_group"] else r["best_group"]]["body"]
        order = sorted(feel, key=feel.get, reverse=True)
        self.assertEqual(order, ["Mbappé", "Nagasato", "Messi", "Ekitiké", "Haaland"], feel)

    def test_women_use_real_height_for_feel_but_own_accelerate_limits(self):
        p = player("Nagasato")                      # 164 cm
        r = rate(p, CFG)
        self.assertGreater(r["feel_parts"]["height"], 0)          # short = bonus, no +17 cm any more
        tall = copy.deepcopy(p)
        tall.height_cm = 170                        # >= 162: too tall for Explosive as a woman
        tall.attributes.update(agility=95, strength=60, acceleration=90)
        self.assertNotEqual(rate(tall, CFG)["accelerate"], "Explosive")

    def test_fc27_bonuses(self):
        from fcrating.model import off_balance_bonus, stand_tackle_bonus
        w = CFG["weights"]
        self.assertGreater(off_balance_bonus(92, "W", w), off_balance_bonus(85, "W", w))
        self.assertEqual(off_balance_bonus(92, "CB", w), 0.0)
        self.assertLess(stand_tackle_bonus({"standing_tackle": 70}, "CB", w), 0)
        self.assertEqual(stand_tackle_bonus({"standing_tackle": 80}, "CB", w), 0)
        self.assertGreater(stand_tackle_bonus({"standing_tackle": 86}, "CB", w), 0)

    def test_pinged_pass_top_for_midfield_not_for_strikers(self):
        p = player("Ekitiké")
        p.playstyles, p.playstyles_plus = [], ["Pinged Pass"]
        q = copy.deepcopy(p)
        q.playstyles_plus = ["Finesse Shot"]
        cm_pinged = playstyle_bonus(p, p.attributes, "CM", CFG["playstyles"])[0]
        st_pinged = playstyle_bonus(p, p.attributes, "ST", CFG["playstyles"])[0]
        st_finesse = playstyle_bonus(q, q.attributes, "ST", CFG["playstyles"])[0]
        self.assertGreater(cm_pinged, st_pinged)
        self.assertGreater(st_finesse, st_pinged)

    def test_intercept_worth_less_with_high_interceptions(self):
        p = player("Meza")
        p.playstyles_plus, p.playstyles = ["Intercept"], []
        low, high = copy.deepcopy(p), copy.deepcopy(p)
        low.attributes["interceptions"], high.attributes["interceptions"] = 78, 95
        lo = playstyle_bonus(low, low.attributes, "CB", CFG["playstyles"])[1][0]
        hi = playstyle_bonus(high, high.attributes, "CB", CFG["playstyles"])[1][0]
        self.assertLess(hi["raw"] / hi["synergy"], lo["raw"] / lo["synergy"])

    def test_haaland_better_striker_than_ekitike(self):
        self.assertGreater(rate(player("Haaland"), CFG, groups=["ST"])["igr"],
                           rate(player("Ekitiké"), CFG, groups=["ST"])["igr"])

    def test_weighted_handles_missing(self):
        score, comp = weighted({"a": 80}, {"a": 0.5, "b": 0.5})
        self.assertEqual(score, 80)
        self.assertEqual(comp, 0.5)

    def test_pinged_pass_is_top_midfield_playstyle(self):
        table = CFG["playstyles"]["playstyles"]
        best = max(table, key=lambda n: table[n]["plus"] if table[n]["category"] != "goalkeeper" else 0)
        self.assertEqual(best, "Pinged Pass")

    def test_playstyle_bonus_capped(self):
        p = player("Nagasato")
        p.playstyles_plus = list(CFG["playstyles"]["playstyles"])[:30]
        p.playstyles = []
        pts, _ = playstyle_bonus(p, p.attributes, "CM", CFG["playstyles"])
        self.assertLessEqual(pts, CFG["playstyles"]["diminishing"]["max_total"])

    def test_synergy_rewards_matching_stats(self):
        good, bad = player("Nagasato"), player("Nagasato")
        good.playstyles, good.playstyles_plus = [], ["Pinged Pass"]
        bad.playstyles, bad.playstyles_plus = [], ["Pinged Pass"]
        bad.attributes.update(short_passing=60, vision=60)
        g, _ = playstyle_bonus(good, good.attributes, "CM", CFG["playstyles"])
        b, _ = playstyle_bonus(bad, bad.attributes, "CM", CFG["playstyles"])
        self.assertGreater(g, b * 2)

    def test_best_chem_not_worse_than_none(self):
        p = player("Nagasato")
        self.assertGreaterEqual(rate(p, CFG, chem="best")["igr"], rate(p, CFG)["igr"])


class EvoTests(unittest.TestCase):
    def test_evo_raises_rating_and_respects_cap(self):
        p = player("Meza")
        evolved = evolved_copy(p, CFG["weights"]["evo"])
        self.assertTrue(all(v <= 95 or v == p.attributes[k] for k, v in evolved.attributes.items()))
        e = evo_potential(p, CFG)
        self.assertGreater(e["igr_after"], e["igr_now"])

    def test_high_rated_cards_are_not_eligible(self):
        e = evo_potential(player("Mbappé"), CFG)     # OVR 91
        self.assertFalse(e["eligible"])
        self.assertIn("OVR", e["reason"])
        self.assertIsNone(e["evo_value"])
        self.assertIsNone(e["igr_after"])

    def test_icons_and_leaks_are_not_eligible(self):
        icon = player("Nagasato")
        icon.ovr = 80
        self.assertIn("Icon", evo_potential(icon, CFG)["reason"])
        leak = player("Meza")
        leak.status = "lekket"
        self.assertFalse(evo_potential(leak, CFG)["eligible"])

    def test_lower_ovr_gets_bigger_boost(self):
        ecfg = CFG["weights"]["evo"]
        low, high = player("Meza"), player("Meza")
        low.ovr, high.ovr = 74, 84
        self.assertGreater(evo_boost(low, ecfg), evo_boost(high, ecfg))
        self.assertEqual(evo_boost(low, ecfg), ecfg["max_boost"])
        e_low, e_high = evo_potential(low, CFG), evo_potential(high, CFG)
        self.assertGreater(e_low["gain"], e_high["gain"])
        self.assertGreater(e_low["ovr_after"], low.ovr)

    def test_rank_after_evo(self):
        players = [player(k) for k in PLAYERS]
        results = [rate(p, CFG) for p in players]
        rank_by_position(results, CFG)
        evos = {p.uid: evo_potential(p, CFG) for p in players}
        rank_evos(evos, results)
        meza = evos[player("Meza").uid]
        self.assertTrue(meza["eligible"])
        self.assertLessEqual(meza["rank_after"], meza["rank_now"])
        self.assertEqual(meza["of"], len([r for r in results if "FB" in r["by_group"]]))
        row = flat_row(next(r for r in results if r["name"] == "Kylian Mbappé"), evos[player("Mbappé").uid])
        self.assertIsNone(row["evo_after"])
        self.assertEqual(row["evo_eligible"], "nei")


SMALL = copy.deepcopy(CFG)
SMALL["weights"]["explain"]["min_pool_size"] = 1   # the example file has only a few cards per position


class ExplainTests(unittest.TestCase):
    def ranked(self, cfg=SMALL):
        players = [player(k) for k in PLAYERS]
        results = [rate(p, cfg) for p in players]
        rank_by_position(results, cfg)
        return {r["name"]: r for r in results}

    def test_small_pools_do_not_claim_percentages(self):
        meza = self.ranked(CFG)["Eric Meza"]
        self.assertTrue(meza["by_group"]["FB"]["why"]["few"])
        text = "\n".join(why_lines(meza, "FB", CFG["weights"]["blend"]["FB"]))
        self.assertIn("For få", text)
        self.assertNotIn("topp", text)

    def test_why_data_and_text(self):
        res = self.ranked()
        mb = res["Kylian Mbappé"]
        why = mb["by_group"]["ST"]["why"]
        for key in ("fp", "pp", "sp", "psp", "s", "w", "tf", "ts"):
            self.assertIn(key, why)
        self.assertEqual(why["pp"], min(r["by_group"]["ST"]["why"]["pp"] for r in res.values() if "ST" in r["by_group"]))
        text = "\n".join(why_lines(mb, "ST", CFG["weights"]["blend"]["ST"]))
        self.assertIn("Plass", text)
        self.assertIn("spisser", text)
        self.assertIn("IGR", text)
        self.assertIn("Fart", text)

    def test_unknown_playstyles_get_median(self):
        base = [player(k) for k in ("Mbappé", "Haaland", "Ekitiké", "Messi")]
        unknown = player("Ekitiké")
        unknown.name, unknown.playstyles, unknown.playstyles_plus = "Ukjent PS", [], []
        unknown.playstyles_complete = False
        results = [rate(p, CFG) for p in base + [unknown]]
        before = results[-1]["by_group"]["ST"]["playstyles"]
        rank_by_position(results, CFG)
        e = results[-1]["by_group"]["ST"]
        self.assertTrue(e.get("ps_estimated"))
        self.assertGreater(e["playstyles"], before)

    def test_report_contains_explanations(self):
        players = [player(k) for k in PLAYERS]
        results = [rate(p, CFG) for p in players]
        rank_by_position(results, CFG)
        evos = {p.uid: evo_potential(p, CFG) for p in players}
        rank_evos(evos, results)
        page = render_html(results, evos, CFG)
        for text in ("Ratingen", "Sterkest", "Utregning og kilde", "Nullstill filtre", "skjulte perler", "to: PS+", "Kroppspoeng"):
            self.assertIn(text, page)
        self.assertIn('"stats":', page)          # position averages for the explanation
        self.assertIn("Beste evo-kandidater", page)
        self.assertNotIn("</script><", page.split("<script>")[1][:-len("</script></body></html>")])


class RunAITests(unittest.TestCase):
    def ranked(self, extra=()):
        players = [player(k) for k in PLAYERS] + list(extra)
        results = [rate(p, CFG) for p in players]
        rank_by_position(results, CFG)
        return {r["name"]: r for r in results}

    def test_geyse_runs_better_than_her_ovr(self):
        res = self.ranked()
        geyse = res["Geyse (FC 25-referanse)"]
        self.assertGreater(geyse["run_ai"]["score"], geyse["ovr"] + 4)
        self.assertEqual(geyse["run_ai"]["body"], "Kvikk og sterk")
        self.assertIn("run", geyse["by_group"]["ST"])
        self.assertIsNone(res["Eric Meza"]["by_group"]["FB"].get("run"))   # backs have no Løps-AI rank
        up = [k for k, _, _ in geyse["by_group"]["ST"]["run"]["up"]]
        self.assertIn("kvikk_sterk", up)

    def test_role_and_work_rate_do_not_count(self):
        from fcrating.runs import features, score
        rc = CFG["weights"]["run_ai"]
        a = player("Ekitiké")
        b = copy.deepcopy(a)
        b.roles = {"ST": {"Advanced Forward": 2}}
        self.assertEqual(rate(a, CFG)["by_group"]["ST"]["skill"], rate(b, CFG)["by_group"]["ST"]["skill"])
        w = dict(rc["weights"])
        self.assertEqual(w["arbeidsrate"], 0.0)       # EA removed work rates in FC 25
        self.assertEqual(score(features(a.attributes, "H", rc), w)[0], score(features(a.attributes, "L", rc), w)[0])
        w["arbeidsrate"] = 0.04                        # if calibration finds it matters, it counts
        self.assertGreater(score(features(a.attributes, "H", rc), w)[0], score(features(a.attributes, "L", rc), w)[0])

    def test_hidden_gem_is_relative_to_same_ovr(self):
        # 40 identical 75-rated strikers and one with much better movement
        base = player("Ekitiké")
        clones = []
        for i in range(40):
            c = copy.deepcopy(base)
            c.name, c.id, c.ovr = f"Klon {i}", str(9000 + i), 75
            c.attributes = {k: v - 10 for k, v in base.attributes.items()}
            clones.append(c)
        gem = copy.deepcopy(clones[0])
        gem.name, gem.id = "Perle", "9999"
        for k in ("positioning", "acceleration", "sprint_speed", "agility", "balance"):
            gem.attributes[k] += 12
        res = self.ranked(clones + [gem])
        self.assertTrue(res["Perle"]["by_group"]["ST"]["run"]["gem"])
        self.assertFalse(res["Klon 3"]["by_group"]["ST"]["run"]["gem"])
        self.assertFalse(res["Kylian Mbappé"]["by_group"]["ST"]["run"]["gem"])  # high Løps-AI but also high OVR

    def test_constant_work_rate_is_ignored(self):
        players = [player(k) for k in PLAYERS]
        for p in players:
            p.work_rate_att, p.work_rate_def = "M", "M"
        results = [rate(p, CFG) for p in players]
        cfg = copy.deepcopy(CFG)
        rank_by_position(results, cfg)
        self.assertIn("arbeidsrate", cfg["weights"]["run_ai"]["dropped"])
        geyse = next(r for r in results if r["name"].startswith("Geyse"))
        self.assertNotIn("arbeidsrate", [x[0] for x in geyse["run_ai"]["parts"]])

    def test_similar_cards(self):
        from fcrating.runs import similar
        res = self.ranked()
        twin = copy.deepcopy(PLAYERS["Geyse (FC 25-referanse)"] if "Geyse (FC 25-referanse)" in PLAYERS else
                             [p for p in PLAYERS.values() if p.name.startswith("Geyse")][0])
        twin.name, twin.rarity = "Tvilling", "Test"
        twin.attributes["agility"] -= 1
        results = list(res.values()) + [rate(twin, CFG)]
        rank_by_position(results, CFG)
        geyse = next(r for r in results if r["name"].startswith("Geyse"))
        hits = similar(geyse, results, CFG, n=3, group="ST")
        self.assertEqual(hits[0][0]["name"], "Tvilling")

    def test_similar_to_several_favourites(self):
        from fcrating.runs import similar_to_all
        res = self.ranked()
        results = list(res.values())
        refs = [res["Kylian Mbappé"], res["Yuki Nagasato"]]
        hits = similar_to_all(refs, results, CFG, n=3)
        names = [r["name"] for r, _ in hits]
        self.assertNotIn("Kylian Mbappé", names)
        self.assertNotIn("Yuki Nagasato", names)
        self.assertTrue(hits and all(d >= 0 for _, d in hits))

    def test_exact_name_first(self):
        from fcrating.cli import _name_matches
        items = [player("Messi"), player("Meza")]
        items[1].name = "Aimar Oroz"
        items[0].name = "Aimar"
        self.assertEqual([p.name for p in _name_matches(items, "aimar")], ["Aimar"])
        self.assertEqual(len(_name_matches(items, "aim")), 2)

    def test_calibration_finds_the_signal(self):
        from fcrating.runs import calibrate
        base = player("Ekitiké")
        labeled = []
        for i, agi in enumerate([70, 75, 80, 85, 90, 95, 72, 88, 78, 92, 83, 76]):
            c = copy.deepcopy(base)
            c.name, c.id = f"Test {i}", str(100 + i)
            c.attributes["agility"] = agi
            c.attributes["positioning"] = 170 - agi        # today's weights favour the wrong cards
            labeled.append(c)
        results = [rate(p, CFG) for p in labeled]
        rank_by_position(results, CFG)
        runs = [r["attributes"]["agility"] / 10 for r in results]   # runs follow agility only
        out = calibrate(list(zip(results, runs)), CFG)
        self.assertGreater(out["corr"]["agility"][0], 0.9)
        self.assertFalse(out["kept"])
        self.assertGreater(out["new"]["agility"], out["old"]["agility"])
        self.assertLess(out["new"]["positioning"], out["old"]["positioning"])
        self.assertAlmostEqual(sum(out["new"].values()), 1.0, places=2)
        self.assertEqual(out["new"]["arbeidsrate"], out["old"]["arbeidsrate"])   # no data: weight kept

    def test_calibration_keeps_weights_without_signal(self):
        from fcrating.runs import calibrate
        base = player("Ekitiké")
        cards = []
        for i, acc in enumerate([70, 75, 80, 85, 90, 95]):
            c = copy.deepcopy(base)
            c.name, c.id = f"Støy {i}", str(200 + i)
            c.attributes["acceleration"] = acc
            cards.append(c)
        results = [rate(p, CFG) for p in cards]
        rank_by_position(results, CFG)
        out = calibrate(list(zip(results, [5, 2, 6, 3, 5, 4])), CFG)   # counts unrelated to the numbers
        self.assertTrue(out["kept"])
        self.assertEqual(out["new"], out["old"])

    def test_split_and_height(self):
        from fcrating.runs import features, short_body_value, sub_scores
        rc = CFG["weights"]["run_ai"]
        self.assertEqual(short_body_value(175, rc), 80)
        self.assertGreater(short_body_value(160, rc), short_body_value(190, rc))
        g = [p for p in PLAYERS.values() if p.name.startswith("Geyse")][0]
        dec, exe = sub_scores(features(g.attributes, None, rc, g.height_cm), rc["weights"], rc)
        self.assertLess(dec, exe)             # her strength is the run itself, not Att. Position
        r = rate(g, CFG)
        self.assertIsNotNone(r["by_group"]["ST"]["run_score"])     # Løps-AI counts in IGR for ST
        self.assertIsNone(rate(player("Meza"), CFG)["by_group"]["FB"]["run_score"])  # not for backs

    def test_work_rate_parsing(self):
        from fcrating.schema import split_work_rates
        from fcrating.specials import apply_work_rates, work_rates_by_player
        self.assertEqual(split_work_rates("High/Low"), ("H", "L"))
        info = local.parse_page_text("Workrates: Medium/High\nAcceleration\n80")
        self.assertEqual(info["work_rates"], "Medium/High")
        p = player("Haaland")
        p.id = "239085"
        table = work_rates_by_player({"1": {"player_id": "239085", "version": "FC 27 Rare Gold", "work_rates": "H/M"},
                                      "2": {"player_id": "239085", "version": "FC 27 Team of the Week Gold",
                                            "work_rates": "L/L"}})
        self.assertEqual(apply_work_rates([p], table), 1)
        self.assertEqual((p.work_rate_att, p.work_rate_def), ("H", "M"))   # base card's work rate wins


class ProfileTests(unittest.TestCase):
    def test_profile_style_and_combo(self):
        from fcrating.profile import ORDER, category_pools, combo_score, parse_categories, style
        players = [player(k) for k in PLAYERS]
        # a pool big enough for percentiles: copies with lower numbers
        for i in range(40):
            c = copy.deepcopy(player("Ekitiké"))
            c.name, c.id, c.ovr = f"Fyll {i}", str(500 + i), 70 + i % 10
            c.attributes = {k: v - 15 + (i % 7) for k, v in c.attributes.items()}
            players.append(c)
        results = [rate(p, SMALL) for p in players]
        rank_by_position(results, SMALL)
        mb = next(r for r in results if r["name"] == "Kylian Mbappé")
        prof = mb["profile"]
        self.assertEqual(set(prof["cats"]), set(ORDER))
        self.assertTrue(prof["style"])
        self.assertTrue(all(isinstance(x, str) for x in prof["likes"]))
        self.assertEqual(parse_categories(["Følelse", "løp,dribling"], CFG), ["feel", "run", "dribble"])
        with self.assertRaises(ValueError):
            parse_categories(["tull"], CFG)
        pools = category_pools(results)
        sc_mb = combo_score(mb, "ST", ["feel", "pace"], pools)
        sc_fill = combo_score(next(r for r in results if r["name"] == "Fyll 0"), "ST", ["feel", "pace"], pools)
        self.assertGreater(sc_mb, sc_fill)
        label, likes = style({"feel": 3, "dribble": 10, "run": 20, "defend": 90}, CFG)
        self.assertEqual(label, "Kvikk dribler og løper")
        self.assertEqual(len(likes), 3)
        self.assertEqual(style({"feel": 60, "pace": 70}, CFG)[0], "Jevn profil")

    def test_run_parts_as_categories(self):
        """Løpsvilje/Løpseffekt can be filtered and ranked on, but never go into the style."""
        from fcrating.profile import category_pools, combo_score, parse_categories, style, style_keys
        players = [player(k) for k in PLAYERS]
        cb = player("Meza")
        cb.name, cb.id, cb.position, cb.alt_positions = "Midtstopper", "999", "CB", []
        results = [rate(p, SMALL) for p in players + [cb]]
        rank_by_position(results, SMALL)
        mb = next(r for r in results if r["name"] == "Kylian Mbappé")
        self.assertEqual(mb["profile"]["cats"]["vilje"], mb["run_ai"]["decision"])
        self.assertEqual(mb["profile"]["cats"]["effekt"], mb["run_ai"]["execution"])
        self.assertEqual(parse_categories(["vilje", "Løpseffekt"], CFG), ["vilje", "effekt"])
        self.assertNotIn("vilje", style_keys(CFG))
        self.assertNotIn("effekt", style_keys(CFG))
        self.assertEqual(style({"vilje": 1, "effekt": 1}, CFG)[0], "Jevn profil")
        self.assertEqual(style({"vilje": 1, "effekt": 2, "pace": 10}, CFG)[0], "Rask spiller")
        # a card with no Løps-AI (centre back) has no value, so it drops out of a combo with them
        cb = next(r for r in results if r["name"] == "Midtstopper")
        self.assertIsNone(cb["profile"]["cats"]["effekt"])
        self.assertIsNone(combo_score(cb, "CB", ["effekt"], category_pools(results)))


class SourceTests(unittest.TestCase):
    def test_parse_ea_page(self):
        info = local.parse_page_text((FIX / "ea_side.txt").read_text(encoding="utf-8"))
        a = info["attributes"]
        self.assertEqual(len(a), 29)
        self.assertEqual(a["dribbling"], 89)  # attribute, not the face stat (90)
        self.assertEqual(a["fk_accuracy"], 93)
        self.assertEqual(a["def_awareness"], 20)
        self.assertEqual(info["height_cm"], 169)
        self.assertEqual(info["weight_kg"], 67)

    def test_parse_futgg_page(self):
        info = local.parse_page_text((FIX / "futgg_side.txt").read_text(encoding="utf-8"))
        a = info["attributes"]
        self.assertEqual(len(a), 29)
        self.assertEqual(a["positioning"], 86)
        self.assertEqual(a["dribbling"], 87)
        self.assertEqual(a["def_awareness"], 28)
        self.assertEqual(info["height_cm"], 190)
        self.assertEqual(info["skill_moves"], 4)
        self.assertEqual(info["weak_foot"], 3)
        self.assertEqual(info["accelerate_source"], "Controlled")
        self.assertEqual(info["body_type"], "Lean Tall")

    def test_parse_easysbc_with_chem_arrows(self):
        a = local.parse_page_text((FIX / "easysbc_side.txt").read_text(encoding="utf-8"))["attributes"]
        self.assertEqual(a["positioning"], 96)
        self.assertEqual(a["finishing"], 99)
        self.assertEqual(a["agility"], 96)

    def test_parse_easysbc_off_balance_value_is_used(self):
        text = (FIX / "easysbc_side.txt").read_text(encoding="utf-8") + "\nOff-Balance Dribbling\n91\n"
        self.assertEqual(local.parse_page_text(text)["off_balance_dribbling"], 91.0)
        p = local.player_from_text(text, "Testspiller", "ST", height_cm=170)
        self.assertEqual(rate(p, CFG)["off_balance_dribbling"], 91.0)

    def test_csv(self):
        players = local.load_csv(str(FIX / "spillere.csv"))
        self.assertEqual(len(players), 1)
        p = players[0]
        self.assertEqual(p.height_cm, 175)
        self.assertEqual(p.attributes["positioning"], 80)
        self.assertEqual(p.playstyles_plus, ["Pinged Pass"])
        self.assertEqual(p.playstyles, ["Technical"])

    def test_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "x.json")
            local.save_json(list(PLAYERS.values()), path)
            again = local.load_json(path)
            self.assertEqual([p.name for p in again], [p.name for p in PLAYERS.values()])
            self.assertEqual(again[0].attributes, list(PLAYERS.values())[0].attributes)

    def test_ea_mapper_is_tolerant(self):
        from fcrating.sources.ea_ratings import map_item
        item = {
            "id": 1, "firstName": "Test", "lastName": "Spiller", "overallRating": 80,
            "position": {"shortLabel": "ST"}, "alternatePositions": [{"shortLabel": "LW"}],
            "height": 178, "gender": {"label": "Female"}, "skillMoves": 4, "weakFootAbility": 5,
            "stats": {"acceleration": {"value": 88}, "sprintSpeed": {"value": 86}, "agility": {"value": 90},
                      "defensiveAwareness": {"value": 30}, "dribbling": {"value": 85}},
            "playStyle": [{"label": "Technical"}], "playStylePlus": [{"label": "Pinged Pass"}],
        }
        p = map_item(item)
        self.assertEqual(p.name, "Test Spiller")
        self.assertEqual(p.position, "ST")
        self.assertEqual(p.alt_positions, ["LW"])
        self.assertEqual(p.gender, "F")
        self.assertEqual(p.attributes["sprint_speed"], 86)
        self.assertEqual(p.attributes["def_awareness"], 30)
        self.assertEqual(p.playstyles_plus, ["Pinged Pass"])
        self.assertEqual(p.weak_foot, 5)


class EaFormatTests(unittest.TestCase):
    """The EA feed format is assumed (FC 24/25 layout); this checks the mapper handles it."""

    def test_player_abilities_and_nested_stats(self):
        from fcrating.sources.ea_ratings import map_item
        item = {
            "id": 231747, "rank": 1, "overallRating": 91, "firstName": "Kylian", "lastName": "Mbappé",
            "commonName": None, "height": 182, "weight": 81, "skillMoves": 5, "weakFootAbility": 4,
            "preferredFoot": 1, "gender": {"id": 0, "label": "Male"},
            "position": {"id": "25", "label": "Striker", "shortLabel": "ST"},
            "alternatePositions": [{"id": "27", "label": "Left Wing", "shortLabel": "LW"}],
            "team": {"label": "Real Madrid", "id": 243}, "nationality": {"label": "France"},
            "stats": {
                "pac": {"value": 96, "diff": 0}, "dri": {"value": 92, "diff": 0},
                "acceleration": {"value": 97, "diff": 0}, "sprintSpeed": {"value": 96, "diff": 0},
                "agility": {"value": 93, "diff": 0}, "strength": {"value": 78, "diff": 0},
                "dribbling": {"value": 92, "diff": 0}, "defensiveAwareness": {"value": 16, "diff": 0},
            },
            "playerAbilities": [
                {"id": "quickstep", "label": "Quick Step+", "type": {"id": "playStylePlus"}},
                {"id": "rapid", "label": "Rapid", "type": {"id": "playStyle"}},
            ],
        }
        p = map_item(item)
        self.assertEqual(p.name, "Kylian Mbappé")
        self.assertEqual(p.ovr, 91)
        self.assertEqual((p.position, p.alt_positions), ("ST", ["LW"]))
        self.assertEqual(p.gender, "M")
        self.assertEqual(p.height_cm, 182)
        self.assertEqual(p.attributes["acceleration"], 97)
        self.assertEqual(p.attributes["dribbling"], 92)
        self.assertEqual(p.attributes["def_awareness"], 16)
        self.assertEqual(p.playstyles_plus, ["Quick Step"])
        self.assertEqual(p.playstyles, ["Rapid"])
        self.assertEqual(p.face_stats, {"pac": 96, "dri": 92})


class PositionRankingTests(unittest.TestCase):
    def test_players_only_ranked_within_their_positions(self):
        from fcrating.model import rank_by_position
        results = [rate(p, CFG) for p in PLAYERS.values()]
        rank_by_position(results, CFG)
        by_name = {r["name"].split()[1]: r for r in results}
        # Meza (RB/RM) is never ranked among strikers; Haaland (ST only) never among wingers
        self.assertNotIn("ST", by_name["Meza"]["by_group"])
        self.assertNotIn("W", by_name["Haaland"]["by_group"])
        st_pool = [r for r in results if "ST" in r["by_group"]]
        ranks = sorted(r["by_group"]["ST"]["rank"] for r in st_pool)
        self.assertEqual(ranks, list(range(1, len(st_pool) + 1)))
        self.assertEqual(by_name["Mbappé"]["pos_rank"], 1)
        self.assertEqual(by_name["Meza"]["position_group"], "FB")

    def test_percentile_tiers_for_big_pools(self):
        from fcrating.model import rank_by_position
        base = player("Ekitiké")
        results = []
        for i in range(100):
            p = copy.deepcopy(base)
            p.name = f"Spiss {i}"
            p.attributes = {k: v - i * 0.2 for k, v in p.attributes.items()}
            results.append(rate(p, CFG))
        rank_by_position(results, CFG)
        tiers = [r["pos_tier"] for r in sorted(results, key=lambda r: r["pos_rank"])]
        self.assertEqual(tiers[0], "S")            # topp 1 %
        self.assertEqual(tiers[4], "A")            # topp 5 %
        self.assertEqual(tiers[14], "B")           # topp 15 %
        self.assertEqual(tiers[34], "C")           # topp 35 %
        self.assertEqual(tiers[99], "D")


if __name__ == "__main__":
    unittest.main()


class SimilarAccelerateTests(unittest.TestCase):
    def test_accelerate_type_counts_in_similarity(self):
        from fcrating.model import load_config
        from fcrating.runs import _sim_value, distance
        rc = load_config()["weights"]["run_ai"]
        from fcrating.runs import _clean
        attrs = {k: 70 for k in _clean(rc["similar"]["features"]) if k not in ("height_cm", "arbeidsrate", "kvikk_sterk", "kort_kropp", "accelerate")}
        a = {"attributes": attrs, "height_cm": 180, "work_rate_att": "M", "accelerate": "Explosive"}
        b = dict(a, accelerate="Lengthy")
        c = dict(a, accelerate="Explosive")
        self.assertEqual(_sim_value(a, "accelerate", rc), 100.0)
        self.assertEqual(_sim_value(b, "accelerate", rc), 0.0)
        stats = {k: (70.0, 10.0) for k in _clean(rc["similar"]["features"])}
        self.assertGreater(distance(a, b, stats, rc), distance(a, c, stats, rc))
