"""Probe 3: the new EA page reader in fcrating, on real pages."""
import json, sys
sys.path.insert(0, ".")
from fcrating.sources import ea_ratings
cfg = ea_ratings.load_sources_config()
ea = dict(cfg["ea_ratings"])
for tmpl, n in (("https://www.ea.com/games/ea-sports-fc/ratings?search=Vetlesen&page={page}", 1),
                ("https://www.ea.com/games/ea-sports-fc/ratings?page={page}", 2)):
    ea["html_url_template"] = tmpl
    players = ea_ratings.fetch_pages(ea, max_pages=n)
    print("=" * 10, tmpl, len(players))
    for p in players[:3]:
        d = p.to_dict()
        print(json.dumps({k: d.get(k) for k in ("id", "name", "ovr", "position", "alt_positions", "height_cm", "weak_foot",
                                                 "skill_moves", "playstyles", "playstyles_plus", "gender", "work_rate_att")}, ensure_ascii=False))
        print("  attrs", len(d.get("attributes") or {}), json.dumps(d.get("attributes"), ensure_ascii=False)[:600])
    print("with alts:", sum(1 for p in players if p.alt_positions), "with 25+ attrs:", sum(1 for p in players if len(p.attributes) >= 25))
