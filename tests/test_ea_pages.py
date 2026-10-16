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


if __name__ == "__main__":
    unittest.main()
