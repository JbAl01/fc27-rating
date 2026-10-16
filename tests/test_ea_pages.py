"""EA's FC 27 ratings pages: players (with alternative positions) read from the JSON in each page."""
import json
import unittest

from fcrating.sources import ea_ratings


def page_html(items, total):
    data = {"props": {"pageProps": {"ratingDetails": {"items": items, "totalItems": total}}}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


def item(pid, name, pos, alts, ovr=71):
    return {"id": pid, "firstName": name, "lastName": "Test", "commonName": None, "overallRating": ovr,
            "position": {"id": "10", "shortLabel": pos, "label": pos},
            "alternatePositions": [{"id": "x", "label": a, "shortLabel": a} for a in alts],
            "height": 180, "skillMoves": 3, "weakFootAbility": 4,
            "stats": {"acceleration": {"value": 82}, "sprintSpeed": {"value": 80}, "finishing": {"value": 60}},
            "playerAbilities": [{"label": "Pinged Pass+"}, {"label": "Relentless"}]}


EA = {"html_url_template": "https://example.test/ratings?page={page}", "delay_seconds": 0}


class EaPagesTests(unittest.TestCase):
    def test_reads_every_page_with_alternative_positions(self):
        pages = {1: page_html([item(1, "A", "CDM", ["RW", "CM", "RM"]), item(2, "B", "ST", [])], 3),
                 2: page_html([item(3, "C", "LB", ["LM"])], 3)}
        calls = []

        def get(url, ua):
            n = int(url.rsplit("=", 1)[1])
            calls.append(n)
            return pages[n]
        players = ea_ratings.fetch_pages(EA, get=get, sleep=lambda s: None, log=lambda *a: None)
        self.assertEqual(calls, [1, 2])
        self.assertEqual([p.name for p in players], ["A Test", "B Test", "C Test"])
        a = players[0]
        self.assertEqual(a.position, "CDM")
        self.assertEqual(a.alt_positions, ["RW", "CM", "RM"])
        self.assertEqual(a.attributes.get("acceleration"), 82)
        self.assertIn("Pinged Pass", a.playstyles_plus)
        self.assertIn("Relentless", a.playstyles)
        self.assertEqual(str(a.id), "1")

    def test_a_page_that_keeps_failing_stops_the_fetch(self):
        def get(url, ua):
            if url.endswith("=2"):
                raise OSError("timeout")
            return page_html([item(1, "A", "CDM", [])] * 2, 10)
        with self.assertRaises(RuntimeError):
            ea_ratings.fetch_pages(EA, get=get, sleep=lambda s: None, log=lambda *a: None)

    def test_page_without_data_is_an_error(self):
        with self.assertRaises(ValueError):
            ea_ratings.next_data("<html>no data</html>")

    def test_height_is_kept_from_the_previous_file(self):
        import tempfile
        from pathlib import Path
        from fcrating.cli import _keep_heights
        from fcrating.sources import local
        from fcrating.schema import Player
        with tempfile.TemporaryDirectory() as d:
            old = Path(d) / "ea.json"
            local.save_json([Player.from_dict({"id": "1", "name": "A", "position": "CDM", "height_cm": 186, "attributes": {}})], str(old))
            new = ea_ratings.map_item(dict(item(1, "A", "CDM", ["CM"]), height=""))
            self.assertIsNone(new.height_cm)
            self.assertEqual(_keep_heights([new], str(old)), 1)
            self.assertEqual(new.height_cm, 186)


if __name__ == "__main__":
    unittest.main()


class ClubInfoTests(unittest.TestCase):
    def test_league_and_nation_from_ea_and_inherited_by_special_cards(self):
        from fcrating.cli import _fill_club_info
        from fcrating.schema import Player
        from fcrating.sources.ea_ratings import map_item
        base = map_item({"id": 238235, "firstName": "Hugo", "lastName": "Vetlesen", "overallRating": 71,
                         "position": {"shortLabel": "CDM"}, "leagueName": "1A Pro League",
                         "team": {"id": 231, "label": "Club Brugge"}, "nationality": {"id": 36, "label": "Norway"},
                         "birthdate": "6/4/2000", "stats": {"acceleration": {"value": 87}}})
        self.assertEqual((base.club, base.league, base.nation), ("Club Brugge", "1A Pro League", "Norway"))
        self.assertEqual(base.birthdate, "2000-06-04")
        self.assertEqual(Player.from_dict(base.to_dict()).league, "1A Pro League")
        special = Player(name="Hugo Vetlesen", position="CDM", attributes={}, id="9", base_id="238235", rarity="TOTW")
        icon = Player(name="Legend", position="ST", attributes={}, rarity="Icon")
        _fill_club_info([base, special, icon])
        self.assertEqual((special.league, special.nation), ("1A Pro League", "Norway"))
        self.assertEqual(special.birthdate, "2000-06-04")
        self.assertEqual(icon.league, "Icons")

    def test_birthdate_with_time_as_ea_sends_it(self):
        from fcrating.schema import parse_birthdate
        self.assertEqual(parse_birthdate("12/20/1998 0:00"), "1998-12-20")
        self.assertEqual(parse_birthdate("6/4/2000 00:00:00"), "2000-06-04")
        self.assertIsNone(parse_birthdate("12/20/1998 noe"))
