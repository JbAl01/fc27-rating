import json, os
from fcrating.sources import fifarosters as fr, local
from fcrating import specials
c = fr.FifaRostersCache("data/cache/fifarosters")
ents = specials.unique_entries(c)
spec = [fid for fid, e in ents if not fr.is_base_version(e["version"])]
base = [(fid, e) for fid, e in ents if fr.is_base_version(e["version"])]
fg = json.load(open("data/cache/futgg/kort.json")) if os.path.exists("data/cache/futgg/kort.json") else {}
print("spesialkort", len(spec), "lest fra FUT.GG", sum(1 for f in spec if f in fg), "ikke funnet", sum(1 for f in spec if fg.get(f, {}).get("missing")))
ea = {str(p.id): p for p in local.load_any("data/ea_players.json")}
def has_h(fid, e): return bool((c.details.get(fid) or {}).get("height_cm")) or bool(getattr(ea.get(str(e.get("player_id"))), "height_cm", None))
print("basekort", len(base), "med høyde", sum(1 for fid, e in base if has_h(fid, e)))
g = [(fid, e) for fid, e in base if e["ovr"] >= 75]
print("gull 75+", len(g), "med høyde", sum(1 for fid, e in g if has_h(fid, e)))
