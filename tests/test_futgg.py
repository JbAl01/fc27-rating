import json
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


class CardBackgroundTests(unittest.TestCase):
    BG = "https://game-assets.fut.gg/cdn-cgi/image/quality=85,width=300,format=auto/2027/rarities-level-0-large/22.%s.png" % ("a1" * 32)

    def test_background_after_own_player_item(self):
        html = ('<img src="https://game-assets.fut.gg/x/2027/player-item/27-111.%s.webp">' % ("b2" * 32)
                + '<img src="%s">' % self.BG)
        out = futgg.card_image(html, "111")
        self.assertIn("rarities-level-0-large/22.", out)
        self.assertIn("width=200", out)

    def test_none_without_page_match(self):
        self.assertIsNone(futgg.card_image("<html></html>", "111"))
        self.assertIsNone(futgg.card_image("x", None))

    def test_player_validates_host(self):
        ok = Player.from_dict({"name": "A", "ovr": 80, "position": "ST", "card_image": self.BG})
        bad = Player.from_dict({"name": "A", "ovr": 80, "position": "ST", "card_image": "https://evil.example/a.png"})
        self.assertEqual(ok.card_image, self.BG)
        self.assertIsNone(bad.card_image)

    def test_badges_need_https(self):
        p = Player.from_dict({"name": "A", "ovr": 80, "position": "ST", "club_image": "https://x/c.png", "nation_image": "javascript:1"})
        self.assertEqual(p.club_image, "https://x/c.png")
        self.assertIsNone(p.nation_image)


class CardFaceTests(unittest.TestCase):
    def test_face_is_this_cards_own_picture(self):
        u = "https://game-assets.fut.gg/cdn-cgi/image/quality=85,width=400,format=auto/2027/player-item/27-%s.%s.webp"
        html = '<img src="%s"><img src="%s">' % (u % ("999", "c3" * 32), u % ("111", "d4" * 32))
        out = futgg.face_image(html, "111")
        self.assertIn("27-111.", out)
        self.assertIn("width=200", out)
        self.assertIsNone(futgg.face_image("<html></html>", "111"))


class LeagueAndFootTests(unittest.TestCase):
    def test_league_image(self):
        u = "https://game-assets.fut.gg/cdn-cgi/image/quality=85,width=80,format=auto/2027/league/53.%s.png" % ("e5" * 32)
        self.assertEqual(futgg.league_image('<img src="%s">' % u), u)
        self.assertIsNone(futgg.league_image("<html></html>"))

    def test_ea_foot_is_a_number(self):
        from fcrating.sources import ea_ratings
        self.assertEqual(ea_ratings._foot(1), "Right")
        self.assertEqual(ea_ratings._foot(2), "Left")
        self.assertEqual(ea_ratings._foot("Left"), "Left")
        self.assertIsNone(ea_ratings._foot(None))


class ApplyImagesTests(unittest.TestCase):
    def test_apply_sets_images_from_cache(self):
        base = "https://game-assets.fut.gg/cdn-cgi/image/quality=85,width=200,format=auto/2027/"
        p = Player.from_dict({"name": "A", "id": "7", "ovr": 80, "position": "ST"})
        rec = {"7": {"ps": ["Rapid"], "psp": [], "img": base + "rarities-level-3-large/0." + "a1" * 32 + ".png",
                     "face": base + "player-item/27-7." + "b2" * 32 + ".webp",
                     "lg": base + "league/53." + "c3" * 32 + ".png", "t": "2026-10-16"}}
        futgg.apply([p], rec)
        self.assertTrue(p.card_image.endswith(".png"))
        self.assertIn("player-item", p.image)
        self.assertIn("/league/", p.league_image)


class IconTests(unittest.TestCase):
    def test_parse_icons_frame_and_symbol_as_on_futgg(self):
        plain = futgg._PLAIN
        html = ('<div title="Pinged Pass"><svg viewBox="0 0 256 256" role="img" height="42" width="42"><path d="%s" fill="currentColor"></path></svg>'
                '<svg role="img" viewBox="0 0 374.94 300.11" height="21" width="21" class="absolute -translate-y-[50%%]">'
                '<path d="M114,255.77c8.05-16.41Z" fill="#000" onclick="x()"></path></svg></div>'
                '<div title="Quick Step"><svg viewBox="0 0 256 256" height="42"><path d="M12.813,104.953L68.157,21.862Z"></path></svg>'
                '<svg viewBox="0 0 259.98 386.12" height="21" class="-translate-y-[65%%]"><path d="M1,2Z"></path><path d="M3,4Z"></path></svg></div>'
                '<div class="small" title="Trickster"><svg height="20" viewBox="0 0 256 256"><path d="M1 1Z"></path></svg></div>') % plain
        icons = futgg.parse_icons(html)
        self.assertEqual(icons["Pinged Pass"], {"vb": "0 0 256 256", "d": [plain], "gvb": "0 0 374.94 300.11",
                                                "g": ["M114,255.77c8.05-16.41Z"], "gs": 0.5, "gy": 50})
        self.assertEqual(icons["Quick Step+"]["g"], ["M1,2Z", "M3,4Z"])
        self.assertEqual(icons["Quick Step+"]["gy"], 65)
        self.assertNotIn("Trickster", icons)
        self.assertNotIn("onclick", json.dumps(icons))


class ColorTests(unittest.TestCase):
    def test_card_colors_from_the_drawn_card_not_the_version_list(self):
        # as on Nuno Mendes' Destined for Glory page: the version list also names an old TOTS card's colours
        html = ('eaId:67361009,overall:89,commonName:"Nuno Mendes",rarityName:"Destined for Glory",x:1,'
                'eaId:1,overall:97,rarityName:"Team of the Season",textColor:"FFEE90",overallColor:"FFEE90",lineColor:"00FEFE",'
                '<div class="fc-card w-full bg-cover" style="color:#ffffff;--color:#ffffff;--fill-color:#2a084f;--overall-color:#ffffff">'
                '<img src="https://game-assets.fut.gg/x/2027/player-item/27-5.ab.webp"/></div>'
                '<div class="fc-card w-full bg-cover relative group is-dynamic" style="color:#fff3cf;--color:#fff3cf;--fill-color:#005256;'
                '--overall-color:#FFF3CF;--position-color:#fff3cf"><img class="absolute" src="https://game-assets.fut.gg/x/2027/rarities/22.ab.png"/>'
                '<img src="https://game-assets.fut.gg/x/2027/player-item/27-67361009.cd.webp" alt="Nuno Mendes"/></div>')
        self.assertEqual(futgg.card_colors(html, "67361009"), "fff3cf/fff3cf/005256")
        self.assertEqual(futgg.card_colors(html, "5"), "ffffff/ffffff/2a084f")
        self.assertIsNone(futgg.card_colors(html, "1"))

    def test_player_card_color_validated(self):
        self.assertEqual(Player.from_dict({"name": "A", "ovr": 80, "position": "ST", "card_color": "2d2410/2d2410/e1be5d"}).card_color, "2d2410/2d2410/e1be5d")
        self.assertIsNone(Player.from_dict({"name": "A", "ovr": 80, "position": "ST", "card_color": "red;x"}).card_color)
