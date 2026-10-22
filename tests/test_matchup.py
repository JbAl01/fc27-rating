"""Matchup (owner 22.10): attacker against defender duel by duel, with the cards after their evo plan."""
import copy
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fcrating import evolab, matchup  # noqa: E402
from fcrating.model import load_config, rank_by_position, rate  # noqa: E402
from fcrating.schema import position_group  # noqa: E402
from fcrating.sources import local  # noqa: E402

CFG = load_config(ROOT / "config")
BASE = local.load_json(str(ROOT / "data" / "eksempel_spillere.json"))


def _setup():
    ps = [copy.deepcopy(p) for p in BASE]
    res = [rate(p, CFG) for p in ps]
    rank_by_position(res, CFG)
    return ps, res


class MatchupTests(unittest.TestCase):
    def test_faster_stronger_defender_holds_better(self):
        s = matchup.settings(CFG)
        att = [95, 90, 80, 90, 80]
        slow = [70, 88, 85, 82, 95]
        fast = [90, 88, 88, 84, 90]
        self.assertGreater(matchup.duel(att, slow, s)["total"], matchup.duel(att, fast, s)["total"])

    def test_one_duel_never_decides_alone(self):
        s = matchup.settings(CFG)
        r = matchup.duel([80, 80, 80, 80, 40], [80, 80, 80, 80, 95], s)   # a small winger in the air
        self.assertGreaterEqual(r["total"], -s["cap"] * s["weights"]["luft"] / sum(s["weights"].values()) - 0.05)

    def test_evo_version_is_listed_with_its_plan(self):
        ps, res = _setup()
        p = next(p for p in ps if position_group(p.position) in matchup.DEF_GROUPS)
        lab = evolab.load_lab_config()
        up = {k: min(99.0, v + 10) for k, v in p.attributes.items()}
        summary = {p.uid: {"live": {"steps": [{"name": "Test-evo"}], "ld": {"a": up, "o": (p.ovr or 70) + 5,
                   "ps": list(p.playstyles), "psp": list(p.playstyles_plus), "wf": p.weak_foot, "sm": p.skill_moves,
                   "r": {}, "rar": p.rarity, "done": []}}}}
        d = matchup.build(ps, res, CFG, summary, lab)
        self.assertEqual(d["n_evo"], 1)
        evo_rows = [r for r in d["def"] if r[8]]
        base_row = next(r for r in d["def"] if not r[8] and d["strings"][r[7]] == p.uid)
        self.assertEqual([d["strings"][i] for i in evo_rows[0][8]], ["Test-evo"])
        self.assertGreater(evo_rows[0][6][0], base_row[6][0])   # faster after the evo

    @unittest.skipUnless(shutil.which("node"), "node mangler")
    def test_page_maths_matches_python(self):
        ps, res = _setup()
        d = matchup.build(ps, res, CFG)
        page = matchup.render(d)
        js = re.search(r"<script>\s*(const D=.*?)</script>", page, re.S).group(1)
        js = js.split("const card=")[0]   # the data and duel() only
        js = js.replace("const D=", "const D=", 1)
        duel_src = re.search(r"function duel\(a,d\)\{.*?\n?return\{g,t:[^}]*\}\}", page, re.S).group(0)
        pairs = [(a[6], f[6]) for a in d["att"][:6] for f in d["def"][:6]]
        script = js + "\n" + duel_src + "\nconsole.log(JSON.stringify(" + json.dumps(pairs) + ".map(([a,f])=>duel({p:a},{p:f}).t)))"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[:400])
        got = json.loads(out.stdout)
        s = matchup.settings(CFG)
        for (a, f), t in zip(pairs, got):
            self.assertAlmostEqual(matchup.duel(a, f, s)["total"], t, delta=0.11)

    def test_tabs_link_the_page(self):
        self.assertIn('href="matchup.html"', (ROOT / "fcrating" / "evolab_page.html").read_text(encoding="utf-8"))
        self.assertIn('href="matchup.html"', (ROOT / "fcrating" / "about_page.html").read_text(encoding="utf-8"))
        from fcrating.site import PAGES
        self.assertIn("matchup.html", PAGES)


if __name__ == "__main__":
    unittest.main()
