"""Base cards without height (EA's FC 27 pages leave it empty) get FIFA Rosters' card page."""
import tempfile
import unittest
from unittest import mock

from fcrating import specials
from fcrating.sources import fifarosters as fr


class FakeFetcher:
    def __init__(self, *a, **k):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return "<html><body><p>Height 165cm</p><p>Acceleration 85</p></body></html>"


CFG = {"specials": {"fifarosters": {"full_list_url": "x", "totw_list_url": "x", "full_scan_days": 7,
                                     "detail_limit_per_run": 0, "height_limit_per_run": 1},
                    "realsport101": {"category_url": "x"}}}


class HeightFetchTests(unittest.TestCase):
    def test_fetches_card_page_for_base_card_without_height_best_first(self):
        with tempfile.TemporaryDirectory() as d:
            cache = fr.FifaRostersCache(d + "/fifarosters")
            for futid, pid, ovr in [("1", "100", 61), ("2", "200", 75), ("3", "300", 80)]:
                cache.entries[futid] = {"name": f"P{pid}", "version": "Rare Bronze", "ovr": ovr, "position": "CAM",
                                        "face": {}, "player_id": pid, "url": f"https://f/{futid}"}
            cache.meta["last_full_scan"] = "2999-01-01T00:00:00"
            cache.save()
            with mock.patch.object(specials, "PoliteFetcher", FakeFetcher), \
                    mock.patch.object(fr, "scan_list", return_value=1):
                fc, _ = specials.run_fetch(CFG, d, leaks=False, log=lambda *a: None, height_known={"300"})
            # 300 already has height; the best of the rest (200, OVR 75) is fetched, limit 1
            self.assertEqual(list(fc.details), ["2"])
            self.assertEqual(fc.details["2"]["height_cm"], 165)


if __name__ == "__main__":
    unittest.main()
