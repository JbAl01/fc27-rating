"""Special cards: FIFA Rosters, RealSport101 and the promo estimator.
Run with:  python -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating.model import load_config, rate  # noqa: E402
from fcrating.net import PoliteFetcher  # noqa: E402
from fcrating.promo import (BaseIndex, build_special, estimate_attributes,  # noqa: E402
                            face_from_attributes, norm_name)
from fcrating.schema import Player  # noqa: E402
from fcrating.sources import fifarosters as fr  # noqa: E402
from fcrating.sources import realsport101 as rs  # noqa: E402
from fcrating import specials  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
CFG = load_config()
FW = CFG["weights"]["face_stats"]

# Bellingham's Team of the Week card as shown on FIFA Rosters
BELLINGHAM_TOTW = {
    "acceleration": 81, "sprint_speed": 80, "agility": 84, "balance": 84, "jumping": 87, "stamina": 94,
    "strength": 82, "reactions": 93, "aggression": 86, "interceptions": 80, "positioning": 91, "vision": 90,
    "ball_control": 92, "crossing": 71, "dribbling": 89, "finishing": 87, "fk_accuracy": 71,
    "heading_accuracy": 78, "long_passing": 88, "short_passing": 91, "def_awareness": 78, "shot_power": 87,
    "long_shots": 90, "standing_tackle": 82, "sliding_tackle": 86, "volleys": 80, "curve": 78, "penalties": 75,
    "composure": 82,   # not on the original sheet; set so DRI fits the FC 27 formula (which has Composure)
}
TOTW_FACE = {"pac": 80, "sho": 87, "pas": 85, "dri": 89, "def": 80, "phy": 86}
BASE_FACE = {"pac": 79, "sho": 86, "pas": 83, "dri": 88, "def": 79, "phy": 85}  # base 90 card


def bellingham_base() -> Player:
    """Base card made by taking the TOTW upgrade back off (TOTW face minus base face)."""
    attrs = dict(BELLINGHAM_TOTW)
    for key, weights in FW.items():
        if key.startswith("_"):
            continue
        d = TOTW_FACE[key] - BASE_FACE[key]
        for a in weights:
            if a in attrs:
                attrs[a] -= d
    attrs["reactions"] -= 1
    return Player(name="Jude Bellingham", position="CAM", alt_positions=["CM", "CDM", "LM"], id="252371",
                  ovr=90, height_cm=186, attributes=attrs, skill_moves=4, weak_foot=4,
                  playstyles=["Technical", "Press Proven"], playstyles_plus=["Incisive Pass"],
                  rarity="Rare")


class FaceStatTests(unittest.TestCase):
    def test_face_weights_reproduce_real_card(self):
        face = face_from_attributes(BELLINGHAM_TOTW, FW)
        self.assertEqual({k: round(v) for k, v in face.items()}, TOTW_FACE)

    def test_estimator_rebuilds_totw_from_base(self):
        base = bellingham_base()
        est = estimate_attributes(base, TOTW_FACE, 91, CFG)
        for key, value in BELLINGHAM_TOTW.items():
            self.assertAlmostEqual(est[key], value, delta=1, msg=key)
        self.assertEqual({k: round(v) for k, v in face_from_attributes(est, FW).items()}, TOTW_FACE)

    def test_estimator_respects_cap(self):
        base = Player(name="X", position="ST", ovr=80,
                      attributes={"acceleration": 98, "sprint_speed": 90})
        est = estimate_attributes(base, {"pac": 97}, 85, CFG)
        self.assertEqual(est["acceleration"], 99)
        self.assertAlmostEqual(0.45 * est["acceleration"] + 0.55 * est["sprint_speed"], 97, delta=0.6)


class NameTests(unittest.TestCase):
    def test_norm_name(self):
        self.assertEqual(norm_name("Martin Ødegaard"), "martin odegaard")
        self.assertEqual(norm_name("Viktor Gyökeres"), "viktor gyokeres")
        self.assertEqual(norm_name("Lionel Messi (FC 26-referanse)"), "lionel messi")

    def test_index_by_id_and_name(self):
        idx = BaseIndex([bellingham_base(), Player(name="Martin Odegaard", position="CAM", attributes={}, ovr=86)])
        self.assertEqual(idx.find(player_id="252371")[0].name, "Jude Bellingham")
        self.assertEqual(idx.find(name="Martin Ødegaard")[0].name, "Martin Odegaard")
        self.assertEqual(idx.find(name="Bellingham")[0].name, "Jude Bellingham")
        self.assertIsNone(idx.find(name="Ukjent Spiller")[0])


class FifaRostersTests(unittest.TestCase):
    def setUp(self):
        self.entries = fr.parse_list_page((FIX / "fifarosters_liste.html").read_text(encoding="utf-8"))

    def test_list_parsing(self):
        self.assertEqual(len(self.entries), 4)
        put, bel, pele, hansen = self.entries
        self.assertEqual((put["ovr"], put["name"], put["position"]), (92, "Alexia Putellas", "CAM"))
        self.assertEqual(put["version"], "FC 27 Team of the Week Gold")
        self.assertEqual(put["face"], {"pac": 81, "sho": 91, "pas": 92, "dri": 93, "def": 73, "phy": 77})
        self.assertEqual((put["player_id"], put["futid"]), ("227203", "50558851"))
        self.assertEqual((bel["name"], bel["position"], bel["version"]), ("Bellingham", "CAM", "FC 27 Team of the Week Gold"))
        self.assertEqual(bel["face"], TOTW_FACE)
        self.assertEqual((bel["skill_moves"], bel["weak_foot"], bel["work_rates"]), (4, 4, "M/M"))
        self.assertEqual(pele["version"], "Icon")
        self.assertEqual(hansen["version"], "FC 27 Rare Gold")
        self.assertTrue(bel["url"].startswith("https://www.fifarosters.com/players?player=252371"))

    def test_base_version_detection(self):
        self.assertTrue(fr.is_base_version("FC 27 Rare Gold"))
        self.assertTrue(fr.is_base_version("Non Rare Silver"))
        self.assertFalse(fr.is_base_version("FC 27 Team of the Week Gold"))
        self.assertFalse(fr.is_base_version("Icon"))

    def test_detail_parsing(self):
        d = fr.parse_detail_page((FIX / "fifarosters_kort.html").read_text(encoding="utf-8"))
        self.assertEqual(d["attributes"], {k: float(v) for k, v in BELLINGHAM_TOTW.items() if k != "composure"})
        self.assertEqual(d["height_cm"], 186)
        self.assertEqual((d["skill_moves"], d["weak_foot"]), (4, 4))

    def test_build_specials_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            fr_cache = fr.FifaRostersCache(str(Path(tmp) / "fr"))
            for e in self.entries:
                fr_cache.entries[e["futid"]] = e
            fr_cache.details["50584019"] = fr.parse_detail_page(
                (FIX / "fifarosters_kort.html").read_text(encoding="utf-8"))
            leak_cache = rs.LeakCache(str(Path(tmp) / "rs"))
            url = "https://realsport101.com/article/fc-27-team-of-the-week-3-leaked"
            leak_cache.articles[url] = {"title": "FC 27 Team of the Week 3 Leaked", "cards": rs.parse_article(
                (FIX / "realsport_artikkel.html").read_text(encoding="utf-8"), "FC 27 Team of the Week 3 Leaked")}
            base = [bellingham_base(), Player(name="Temwa Chawinga", position="LM", gender="F", ovr=88, id="1",
                                              height_cm=165, attributes=dict(BELLINGHAM_TOTW))]
            cards, problems = specials.build_specials(base, fr_cache, leak_cache, CFG)

        by = {(c.name, c.status): c for c in cards}
        bel = by[("Jude Bellingham", "utgitt")]
        self.assertFalse(bel.estimated)                     # full attributes from the card page
        self.assertEqual(bel.rarity, "FC 27 Team of the Week Gold")
        self.assertEqual(bel.playstyles_plus, ["Incisive Pass"])   # PlayStyles inherited from base
        self.assertEqual(bel.roles["CAM"], {"alle roller (spesialkort)": 2})
        self.assertNotIn(("Jude Bellingham", "lekket"), by)  # leak dropped: same card is released
        cha = by[("Temwa Chawinga", "lekket")]
        self.assertTrue(cha.estimated)
        self.assertIn("Rapid", cha.playstyles_plus)
        self.assertEqual(cha.gender, "F")
        self.assertEqual(cha.ovr, 90)
        names = {c.name for c in cards}
        self.assertNotIn("Graham Hansen", names)            # base card skipped
        self.assertTrue(any("Pelé" in p for p in problems))  # Icon without base or card page waits
        self.assertTrue(any("Ødegaard" in p for p in problems))  # no base card in this test set
        r = rate(bel, CFG)
        self.assertIn("CAM", r["by_group"])
        self.assertEqual(r["status"], "utgitt")


class FC27BaseTests(unittest.TestCase):
    def test_fc27_base_cards_replace_older_ea_cards(self):
        entries = fr.parse_list_page((FIX / "fifarosters_liste.html").read_text(encoding="utf-8"))
        hansen = next(e for e in entries if "Rare Gold" in e["version"])
        old_ea = Player(name="Caroline Graham Hansen", position="RW", id=hansen["player_id"], ovr=hansen["ovr"] - 3,
                        gender="F", height_cm=171, attributes=dict(BELLINGHAM_TOTW), playstyles=["Technical"],
                        roles_complete=False, source="ea-ratings")
        with tempfile.TemporaryDirectory() as tmp:
            cache = fr.FifaRostersCache(str(Path(tmp) / "fr"))
            for e in entries:
                cache.entries[e["futid"]] = e
            cards, _ = specials.build_specials([old_ea], cache, None, CFG, include_base=True)
        base = next(c for c in cards if c.source == specials.FC27_BASE_SOURCE)
        self.assertEqual(base.ovr, hansen["ovr"])                 # FC 27 rating, not the older one
        self.assertIsNone(base.status)                            # a base card, not a special
        self.assertEqual(base.roles, {})                          # no special-card ++ in every role
        self.assertEqual(base.playstyles, ["Technical"])          # PlayStyles from the older card
        self.assertTrue(base.estimated)
        kept, msg = specials.prefer_fc27_base([old_ea, base])
        self.assertEqual(kept, [base])                            # the older EA card is replaced
        self.assertIn("FC 27", msg)
        other = Player(name="Andre", position="ST", id="1", attributes={}, source="ea-ratings")
        self.assertEqual(specials.prefer_fc27_base([old_ea, base, other], min_cards=10)[0], [base, other])
        kept = specials.prefer_fc27_base([old_ea, base, other], min_cards=1)[0]
        # a card FIFA Rosters' list lacks is rated from EA's own card, so a whole OVR tier never disappears
        self.assertEqual([c.name for c in kept], [base.name, "Andre"])
        self.assertEqual(kept[1].rarity, "FC 27 Common Bronze")


class EaAttributeTests(unittest.TestCase):
    def test_base_card_takes_ea_attributes_only_when_it_is_the_same_card(self):
        face = {"pac": 86, "sho": 62, "pas": 59, "dri": 72, "def": 32, "phy": 59}
        ea = Player(name="Jesse Eugen Bisiwu", position="LW", id="88043", ovr=67, face_stats=dict(face),
                    attributes={"acceleration": 87, "sprint_speed": 86}, source="ea-ratings")
        fr_card = Player(name="Jesse Eugen Bisiwu", position="LW", id="88043", ovr=67, face_stats=dict(face),
                         attributes={"acceleration": 87, "sprint_speed": 76, "composure": 67},
                         source=specials.FC27_BASE_SOURCE)
        other = Player(name="X", position="ST", id="5", ovr=80, face_stats={"pac": 90}, attributes={"sprint_speed": 70},
                       source=specials.FC27_BASE_SOURCE)
        ea_other = Player(name="X", position="ST", id="5", ovr=81, face_stats={"pac": 91}, attributes={"sprint_speed": 91},
                          source="ea-ratings")
        n = specials.ea_attributes_for_base_cards([ea, fr_card, other, ea_other])
        self.assertEqual(n, 1)
        self.assertEqual(fr_card.attributes["sprint_speed"], 86)      # EA's, as on the card (PAC 86)
        self.assertEqual(fr_card.attributes["composure"], 67)         # kept where EA has none
        self.assertEqual(other.attributes["sprint_speed"], 70)        # EA has another version: untouched
        self.assertTrue(specials.same_card(ea, 67, face))
        self.assertFalse(specials.same_card(ea, 68, face))


class PromoPageTests(unittest.TestCase):
    def test_other_game_versions_are_skipped(self):
        html = (FIX / "fifarosters_liste.html").read_text(encoding="utf-8")
        old = html.replace("&v=27", "&v=17", 1)          # first card now links to FIFA 17
        self.assertEqual(len(fr.parse_list_page(old)), len(fr.parse_list_page(html)) - 1)

    def test_promo_scan_tries_address_forms_until_fc27_cards_show(self):
        html = (FIX / "fifarosters_liste.html").read_text(encoding="utf-8")
        fifa17 = html.replace("&amp;v=27", "&amp;v=17").replace("&v=27", "&v=17")

        class FakeFetcher:
            def __init__(self):
                self.urls = []

            def get(self, url):
                self.urls.append(url)
                if ".php?&pageNum=" in url:
                    return fifa17                      # first form shows an old edition
                if ".php?v=27&pageNum=1" in url:
                    return html                        # second form shows FC 27
                return "<html></html>"

        with tempfile.TemporaryDirectory() as tmp:
            cache = fr.FifaRostersCache(str(Path(tmp) / "fr"))
            fetcher, log = FakeFetcher(), []
            found = specials.scan_promo(fetcher, cache, "fut-future-stars", 5, log.append)
        self.assertEqual(found, len(fr.parse_list_page(html)))
        self.assertTrue(any("ingen fra FC 27" in m for m in log))
        self.assertTrue(all("v=17" not in e["url"] for e in cache.entries.values()))

    def test_promo_url(self):
        want = "https://www.fifarosters.com/fut-future-stars.php?&pageNum={page}"
        for raw in ("fut-future-stars", "https://www.fifarosters.com/fut-future-stars", "fut-future-stars.php", want):
            self.assertEqual(specials.promo_url(raw), want)


class IconMatchTests(unittest.TestCase):
    def test_icon_never_takes_a_namesakes_base_card(self):
        entries = fr.parse_list_page((FIX / "fifarosters_liste.html").read_text(encoding="utf-8"))
        pele = next(e for e in entries if e["version"] == "Icon")
        namesake = Player(name=pele["name"], position="ST", id="1", ovr=60, attributes=dict(BELLINGHAM_TOTW),
                          playstyles=["Bruiser"], rarity="Common")
        with tempfile.TemporaryDirectory() as tmp:
            fr_cache = fr.FifaRostersCache(str(Path(tmp) / "fr"))
            fr_cache.entries[pele["futid"]] = pele
            fr_cache.details[pele["futid"]] = {"attributes": dict(BELLINGHAM_TOTW), "height_cm": 173}
            cards, _ = specials.build_specials([namesake], fr_cache, None, CFG)
        icon = next(c for c in cards if c.rarity == "Icon")
        self.assertEqual(icon.playstyles, [])                # nothing inherited from the namesake
        self.assertFalse(icon.playstyles_complete)          # so PlayStyles get estimated instead

    def test_exact_name_only_when_id_is_unknown(self):
        idx = BaseIndex([Player(name="Rodrigo Hernández", position="CDM", id="5", ovr=90, attributes={})])
        self.assertIsNone(idx.find(name="Rodri Hernández", player_id="999", exact_name=True)[0])
        self.assertIsNotNone(idx.find(name="Rodrigo Hernández", player_id="999", exact_name=True)[0])

    def test_namesake_with_other_id_is_not_matched(self):
        bruno = Player(name="Bruno Fernandes", position="CAM", id="212198", ovr=87, foot="Right",
                       attributes={}, playstyles=["Incisive Pass"])
        idx = BaseIndex([bruno])
        # a 56-rated Bruno Fernandes with his own id: OVR doesn't fit
        self.assertIsNone(idx.find(name="Bruno Fernandes", player_id="777", exact_name=True,
                                   ovr=56, base_card=True)[0])
        self.assertIsNone(idx.find(name="Bruno Fernandes", player_id="777", exact_name=True, ovr=56)[0])
        # the base card's id is used by another player in the source
        self.assertIsNone(idx.find(name="Bruno Fernandes", player_id="777", exact_name=True, ovr=88,
                                   other_ids={"212198", "777"})[0])
        # other foot
        self.assertIsNone(idx.find(name="Bruno Fernandes", player_id="777", exact_name=True, ovr=88,
                                   foot="Left")[0])
        # same player with an unknown id and fitting OVR is still matched
        self.assertIsNotNone(idx.find(name="Bruno Fernandes", player_id="777", exact_name=True, ovr=89,
                                      foot="Right", other_ids={"777"})[0])

    def test_build_specials_skips_namesake_base(self):
        bruno = Player(name="Bruno Fernandes", position="CAM", id="212198", ovr=87, foot="Right",
                       attributes=dict(BELLINGHAM_TOTW), playstyles=["Incisive Pass"], rarity="Rare")
        other = {"ovr": 56, "name": "Bruno Fernandes", "position": "CB", "version": "Team of the Week",
                 "work_rates": "M/M", "skill_moves": 2, "weak_foot": 3, "foot": "Right",
                 "face": {"pac": 60, "sho": 30, "pas": 40, "dri": 45, "def": 58, "phy": 62},
                 "player_id": "999001", "futid": "5551", "url": "https://www.fifarosters.com/player.php?futid=5551"}
        with tempfile.TemporaryDirectory() as tmp:
            fr_cache = fr.FifaRostersCache(str(Path(tmp) / "fr"))
            fr_cache.entries["5551"] = other
            cards, problems = specials.build_specials([bruno], fr_cache, None, CFG)
        self.assertEqual([c for c in cards if c.ovr == 56], [])   # nothing to build without his card page
        self.assertTrue(any("Bruno Fernandes" in p for p in problems))


class DuplicateTests(unittest.TestCase):
    def test_same_card_listed_twice_is_kept_once(self):
        entries = fr.parse_list_page((FIX / "fifarosters_liste.html").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            fr_cache = fr.FifaRostersCache(str(Path(tmp) / "fr"))
            for e in entries:
                fr_cache.entries[e["futid"]] = e
            bel = next(e for e in entries if e["name"] == "Bellingham")
            copy_ = dict(bel, futid="99999999", url=bel["url"].replace(bel["futid"], "99999999"))
            fr_cache.entries = {"99999999": copy_, **fr_cache.entries}  # copy without card page comes first
            fr_cache.details["50584019"] = fr.parse_detail_page(
                (FIX / "fifarosters_kort.html").read_text(encoding="utf-8"))
            self.assertEqual(len(specials.unique_entries(fr_cache)), len(entries))
            cards, _ = specials.build_specials([bellingham_base()], fr_cache, None, CFG)
        bels = [c for c in cards if c.name == "Jude Bellingham"]
        self.assertEqual(len(bels), 1)
        self.assertFalse(bels[0].estimated)                 # the copy with the card page was kept

    def test_other_version_is_not_a_duplicate(self):
        entries = fr.parse_list_page((FIX / "fifarosters_liste.html").read_text(encoding="utf-8"))
        bel = next(e for e in entries if e["name"] == "Bellingham")
        other = dict(bel, version="FC 27 Team of the Season", ovr=94)
        self.assertNotEqual(specials.card_key(bel), specials.card_key(other))


class RealSportTests(unittest.TestCase):
    def test_article_table(self):
        cards = rs.parse_article((FIX / "realsport_artikkel.html").read_text(encoding="utf-8"),
                                 "FC 27 Team of the Week 3 Leaked: Ødegaard & Chawinga")
        self.assertEqual(len(cards), 4)
        c = cards[0]
        self.assertEqual((c["name"], c["ovr"], c["ps_plus"]), ("Temwa Chawinga", 90, ["Rapid"]))
        self.assertEqual(c["face"], {"pac": 92, "sho": 84, "pas": 83, "dri": 87, "def": 47, "phy": 86})
        self.assertEqual(c["version"], "Team of the Week 3")
        self.assertEqual(cards[2]["ps_plus"], [])

    def test_category_links(self):
        links = rs.article_links((FIX / "realsport_kategori.html").read_text(encoding="utf-8"))
        urls = [l["url"] for l in links]
        self.assertIn("https://realsport101.com/article/fc-27-team-of-the-week-3-leaked-degaard-chawinga-lead-massive-new-squad", urls)
        self.assertIn("https://realsport101.com/article/fc-27-future-stars-team-1-all-leaked-players-start-time", urls)
        self.assertFalse(any("wonderkids" in u or "evolution" in u for u in urls))

    def test_version_from_title(self):
        self.assertEqual(rs.version_from_title("FC 27 Future Stars Team 1: All Leaked Players"), "Future Stars Team 1")
        self.assertEqual(rs.version_from_title("FC 27 Destined for Glory Team 2 Leaked"), "Destined for Glory Team 2")


class PoliteFetcherTests(unittest.TestCase):
    def test_robots_rules_are_respected(self):
        from fcrating.net import Robots
        f = PoliteFetcher()
        f._robots["https://example.com"] = Robots("User-agent: *\nDisallow: /private")
        self.assertTrue(f.allowed("https://example.com/totw.php?pageNum=1"))
        self.assertFalse(f.allowed("https://example.com/private/x"))

    def test_stops_at_the_time_limit(self):
        from fcrating.net import Blocked
        f = PoliteFetcher(deadline=1.0)   # long past
        with self.assertRaises(Blocked):
            f.get("https://example.com/x")

    def test_robots_wildcards(self):
        from fcrating.net import Robots
        r = Robots("User-agent: Other\nDisallow:\n\nUser-agent: *\nDisallow: /api/*\nAllow: /club/$\nDisallow: /club/")
        ua = "fc27-rating/0.3 (personlig bruk)"
        self.assertFalse(r.can_fetch(ua, "https://x.com/api/fut/1/"))
        self.assertTrue(r.can_fetch(ua, "https://x.com/players/1/27-2/"))
        self.assertTrue(r.can_fetch(ua, "https://x.com/club/"))
        self.assertFalse(r.can_fetch(ua, "https://x.com/club/7"))

if __name__ == "__main__":
    unittest.main()
