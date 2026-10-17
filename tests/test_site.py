import re
import tempfile
import unittest
from pathlib import Path

from fcrating import site
from fcrating.cli import main

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = str(ROOT / "data" / "eksempel_spillere.json")
EXTERNAL = re.compile(r"<(?:link|script)\b[^>]*(?:href|src)=[\"']?(?:https?:)?//", re.I)


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "output"
        cls.dest = Path(cls.tmp.name) / "site"
        main(["rate", SAMPLE, "--out", str(cls.out), "--top", "1", "--ignorer-brukte"])
        cfg = {"eier": "Testperson", "kontakt": "venn@example.com", "innlogging": "cloudflare-access",
               "cloudflare_prosjekt": "test"}
        cls.res = site.publish(cls.out, cls.dest, cfg)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_output_has_assets_and_about_page(self):
        for name in ("om.html", "fonts/fonts.css", "fonts/OFL.txt", "manifest.webmanifest", "icon.svg", "icon-180.png"):
            self.assertTrue((self.out / name).exists(), name)

    def test_site_has_pages_but_no_raw_data(self):
        files = set(self.res["files"])
        for name in ("index.html", "rapport.html", "evolab.html", "om.html", "robots.txt", "_headers"):
            self.assertIn(name, files)
        self.assertFalse([f for f in files if f.endswith((".csv", ".json", ".pkl"))])
        self.assertEqual((self.dest / "index.html").read_bytes(), (self.dest / "rapport.html").read_bytes())

    def test_nothing_is_loaded_from_other_sites(self):
        for page in self.dest.glob("*.html"):
            text = page.read_text(encoding="utf-8")
            self.assertNotIn("googleapis", text, page.name)
            self.assertNotIn("gstatic", text, page.name)
            self.assertIsNone(EXTERNAL.search(text), page.name)
        css = (self.dest / "fonts" / "fonts.css").read_text(encoding="utf-8")
        for url in re.findall(r"url\(([^)]+)\)", css):
            self.assertTrue((self.dest / "fonts" / url.strip("'\"")).exists(), url)

    def test_disclaimer_and_privacy(self):
        for name in ("rapport.html", "evolab.html", "om.html"):
            text = (self.dest / name).read_text(encoding="utf-8")
            self.assertIn("ikke godkjent av eller tilknyttet EA", text, name)
        about = (self.dest / "om.html").read_text(encoding="utf-8")
        self.assertIn("not endorsed by or affiliated with EA or its licensors", about)
        self.assertIn("localStorage", about)
        self.assertIn("CF_Authorization", about)
        self.assertIn('href="mailto:venn@example.com"', about)
        self.assertNotIn("__", re.sub(r"<style>.*?</style>", "", about, flags=re.S))

    def test_robots_and_headers(self):
        self.assertIn("Disallow: /", (self.dest / "robots.txt").read_text())
        headers = (self.dest / "_headers").read_text()
        self.assertIn("X-Robots-Tag: noindex", headers)
        self.assertIn("Content-Security-Policy: default-src 'self'", headers)
        self.assertIn("frame-ancestors 'none'", headers)
        for page in ("rapport.html", "evolab.html", "om.html"):
            self.assertIn('name="robots" content="noindex', (self.dest / page).read_text(encoding="utf-8"))

    def test_empty_contact_gives_warning_and_neutral_text(self):
        with tempfile.TemporaryDirectory() as d:
            res = site.publish(self.out, Path(d) / "s", {"eier": "", "kontakt": "", "innlogging": ""})
            self.assertTrue(any("Kontakt" in w for w in res["warnings"]))
            about = (Path(d) / "s" / "om.html").read_text(encoding="utf-8")
            self.assertIn("eierens egen maskin", about)
            self.assertNotIn("CF_Authorization", about)

    def test_refuses_to_empty_a_folder_it_did_not_make(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "viktig.txt").write_text("x")
            with self.assertRaises(SystemExit):
                site.publish(self.out, Path(d), {"kontakt": "x"})
            self.assertTrue((Path(d) / "viktig.txt").exists())

    def test_publishing_twice_replaces_the_folder(self):
        (self.dest / "gammel.txt").write_text("x")
        site.publish(self.out, self.dest, {"kontakt": "x", "eier": "y", "innlogging": "cloudflare-access"})
        self.assertFalse((self.dest / "gammel.txt").exists())
        self.assertTrue((self.dest / "index.html").exists())

    def test_big_page_gets_data_in_separate_files(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "evolab.html"
            page.write_text((self.out / "evolab.html").read_text(encoding="utf-8"), encoding="utf-8")
            text = page.read_text(encoding="utf-8")
            start = text.index("const RAW=") + len("const RAW=")
            rows = json.JSONDecoder().raw_decode(text, start)[0]
            names = site.split_data(page, limit=1000, chunk=2000)
            self.assertGreater(len(names), 1)
            new = page.read_text(encoding="utf-8")
            self.assertIn("const RAW=window.__RAW_EVOLAB||[]", new)
            raw_at = new.index("const RAW=window.__RAW_EVOLAB")
            self.assertLess(new.index(f'<script src="{names[-1]}">'), new.rindex("<script>", 0, raw_at))
            back = []
            for n in names:
                js = (Path(d) / n).read_text(encoding="utf-8").strip()
                self.assertTrue(js.startswith("window.__RAW_EVOLAB=(window.__RAW_EVOLAB||[]).concat("))
                back += json.loads(js[js.index(".concat(") + 8:-2])
            self.assertEqual(back, rows)
            self.assertEqual(site.split_data(Path(d) / names[0].replace("-data-1.js", ".html")), [])

    def test_open_site_text(self):
        about = site.render_about({"eier": "A", "kontakt": "a@example.com", "innlogging": "åpen"})
        self.assertIn("åpen for alle som har lenken", about)
        self.assertIn("GitHub Pages", about)
        self.assertNotIn("CF_Authorization", about)
        self.assertNotIn("__", re.sub(r"<style>.*?</style>", "", about, flags=re.S))

    def test_settings_file_overrides_defaults(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "side.json"
            p.write_text(json.dumps({"_info": "x", "eier": " Ola ", "kontakt": "ola@example.com"}), encoding="utf-8")
            cfg = site.site_config(p)
            self.assertEqual(cfg["eier"], "Ola")
            self.assertEqual(cfg["cloudflare_prosjekt"], "fc27-rating")
            self.assertNotIn("_info", cfg)


if __name__ == "__main__":
    unittest.main()
