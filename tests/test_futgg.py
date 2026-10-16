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


class PlayerPageTests(unittest.TestCase):
    def test_link_to_the_card_on_futgg(self):
        base = Player(name="Bruno Fernandes", position="CAM", attributes={}, id="212198")
        special = Player(name="Bruno Fernandes", position="CAM", attributes={}, id="50544966", base_id="212198")
        icon = Player(name="Pelé", position="CAM", attributes={}, id="67345931",
                      url="https://www.fifarosters.com/players?player=237067&futid=67345931&v=27")
        leak = Player(name="Lekket", position="ST", attributes={})
        self.assertEqual(futgg.player_page(base), "https://www.fut.gg/players/212198/27-212198/")
        self.assertEqual(futgg.player_page(special), "https://www.fut.gg/players/212198/27-50544966/")
        self.assertEqual(futgg.player_page(icon), "https://www.fut.gg/players/237067/27-67345931/")
        self.assertIsNone(futgg.player_page(leak))


ROLE_PAGE = ('<html>position:25,alternativePositionIds:$R[24]=[27],rolesPlus:$R[27]=[43],rolesPlusPlus:$R[28]=[139,141],'
             'scores:$R[103]=[$R[104]={role:63,chemistryStyle:1,score:90.1,rank:2,isPlus:!1,isPlusPlus:!0},'
             '$R[105]={role:66,chemistryStyle:1,score:88,rank:9,isPlus:!0,isPlusPlus:!1},'
             '$R[106]={role:56,chemistryStyle:1,score:87,rank:4,isPlus:!1,isPlusPlus:!0},'
             '$R[107]={role:99,chemistryStyle:1,score:80,rank:40,isPlus:!1,isPlusPlus:!1},'
             '$R[108]={role:63,chemistryStyle:2,score:89,rank:3,isPlus:!1,isPlusPlus:!1}]</html>')


class RoleTests(unittest.TestCase):
    def test_roles_on_base_card(self):
        from fcrating.model import load_config, rate
        rec = futgg.parse_card_page(ROLE_PAGE)
        self.assertEqual(rec["roles"]["r"], {"63": 2, "66": 1, "56": 2, "99": 0})
        self.assertTrue(rec["no_ps"])
        rec["kind"] = "base"
        rp = futgg.load_role_positions()
        self.assertEqual(futgg.roles_from(rec, rp, "ST"), {"ST": {"": 2}, "LW": {"": 2}})
        card = Player(name="Mbappé", position="ST", alt_positions=["LW"], attributes={"finishing": 90}, id="231747",
                      playstyles=["Rapid"], roles_complete=False)
        self.assertEqual(futgg.apply([card], {"231747": rec}, rp), 1)
        self.assertEqual(card.playstyles, ["Rapid"])          # EA's PlayStyles are kept for base cards
        self.assertTrue(card.roles_complete)
        r = rate(card, load_config(), groups=["ST"])
        self.assertEqual(r["by_group"]["ST"]["role"], load_config()["weights"]["roles"]["points"]["2"])

    def test_keeper_roles_from_the_lists(self):
        rec = {"roles": {"r": {}, "p": [], "pp": [145], "pos": 0}, "kind": "base"}
        self.assertEqual(futgg.roles_from(rec, futgg.load_role_positions(), "GK"), {"GK": {"": 2}})


if __name__ == "__main__":
    unittest.main()
