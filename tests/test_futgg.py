"""PlayStyles and height from FUT.GG's card data."""
import json
import tempfile
import unittest

from fcrating.schema import Player
from fcrating.sources import futgg

PS = {"data": [{"eaId": 37, "name": "Gamechanger", "isPlayStylePlus": False},
               {"eaId": 9, "name": "Whipped Pass", "isPlayStylePlus": False},
               {"eaId": 16, "name": "Technical", "isPlayStylePlus": False}]}
TOTW = {"data": {"overall": 80, "playstyles": [37, 9], "playstylesPlus": [16], "height": 176, "weight": 75,
                 "accelerateType": "CONTROLLED", "skillMoves": 3, "weakFoot": 5}}


class Fetcher:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return json.dumps(PS if "playstyles" in url else TOTW)


class FutggTests(unittest.TestCase):
    def test_fetch_once_and_apply_to_special_card(self):
        with tempfile.TemporaryDirectory() as d:
            cache = futgg.FutggCache(d)
            f = Fetcher()
            self.assertEqual(futgg.fetch_items(f, cache, ["50600001", "50600001"], 10, log=lambda *a: None), 1)
            self.assertEqual(futgg.fetch_items(f, cache, ["50600001"], 10, log=lambda *a: None), 0)
            self.assertEqual(len([u for u in f.urls if "item-definitions" in u]), 1)
            card = Player(name="Nicolò Cambiaghi", position="CAM", attributes={}, id="50600001", ovr=80,
                          playstyles=["Gamechanger", "Whipped Pass"], ps_from_base=True)
            self.assertEqual(futgg.apply([card], futgg.load_cards(d)), 1)
            self.assertEqual(card.playstyles, ["Gamechanger", "Whipped Pass"])
            self.assertEqual(card.playstyles_plus, ["Technical"])
            self.assertFalse(card.ps_from_base)
            self.assertEqual(card.height_cm, 176)

    def test_other_card_version_is_not_used(self):
        card = Player(name="X", position="CAM", attributes={}, id="1", ovr=76, playstyles=["Gamechanger"])
        self.assertEqual(futgg.apply([card], {"1": {"ovr": 80, "ps": ["Technical"], "psp": []}}), 0)
        self.assertEqual(card.playstyles, ["Gamechanger"])


if __name__ == "__main__":
    unittest.main()
