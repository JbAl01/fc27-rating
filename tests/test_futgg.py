"""PlayStyles for special cards from the card's page on FUT.GG."""
import tempfile
import unittest

from fcrating.schema import Player
from fcrating.sources import futgg

D = "M128,12.808L243.192,128,128,243.192,12.808,128Z"
O = "M12.813,104.953L68.157,21.862H188.143l55.045,83.091L128,235.138Z"


def icon(name, path=D, h=42, cls=None):
    c = f' class="{cls}"' if cls is not None else ""
    return f'<div{c} title="{name}"><svg viewBox="0 0 256 256" role="img" height="{h}" width="{h}"><path d="{path}" fill-opacity="1"></path></svg></div>'


PAGE = ("<html>" + icon("Low Driven", O) + icon("Gamechanger") + icon("Pinged Pass") + icon("Whipped Pass")
        + "<p>other</p>" + icon("Finesse Shot", h=36, cls="opacity-30") + icon("Gamechanger", h=36, cls="")
        + icon("Technical", h=36, cls="opacity-30")
        + '<div><span>Height</span><span>176cm (5\'9")</span></div></html>')


class Fetcher:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return PAGE


class FutggTests(unittest.TestCase):
    def test_parse_card_page(self):
        rec = futgg.parse_card_page(PAGE)
        self.assertEqual(rec["ps"], ["Gamechanger", "Pinged Pass", "Whipped Pass"])
        self.assertEqual(rec["psp"], ["Low Driven Shot"])
        self.assertEqual(rec["height"], 176)
        self.assertIsNone(futgg.parse_card_page("<html>no icons</html>"))

    def test_fetch_once_and_apply_to_special_card(self):
        with tempfile.TemporaryDirectory() as d:
            cache = futgg.FutggCache(d)
            f = Fetcher()
            self.assertEqual(futgg.fetch_cards(f, cache, [("268703", "50600351")] * 2, 10, log=lambda *a: None), 1)
            self.assertEqual(futgg.fetch_cards(f, cache, [("268703", "50600351")], 10, log=lambda *a: None), 0)
            self.assertEqual(f.urls, ["https://www.fut.gg/players/268703/27-50600351/"])
            card = Player(name="Nicolò Cambiaghi", position="CAM", attributes={}, id="50600351", ovr=80,
                          playstyles=["Gamechanger", "Whipped Pass"], ps_from_base=True)
            self.assertEqual(futgg.apply([card], futgg.load_cards(d)), 1)
            self.assertEqual(card.playstyles, ["Gamechanger", "Pinged Pass", "Whipped Pass"])
            self.assertEqual(card.playstyles_plus, ["Low Driven Shot"])
            self.assertFalse(card.ps_from_base)
            self.assertEqual(card.height_cm, 176)


if __name__ == "__main__":
    unittest.main()
