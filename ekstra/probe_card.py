import json, collections
from fcrating import cli
from fcrating.model import load_config
from fcrating.evolab import face_value
log = open("/tmp/an.txt", "w")
def w(*a): log.write(" ".join(str(x) for x in a) + "\n"); log.flush()
def load(f):
    d = json.load(open(f)); return d if isinstance(d, list) else d.get("players", [])
ea = load("data/ea_players.json"); sp = load("data/spesialkort.json")
w("ea", len(ea), json.load(open("data/ea_players.meta.json")))
for src, ps in (("ea", ea), ("sp", sp)):
    for p in ps:
        if "Bisiwu" in p["name"]:
            w(src, p["name"], p["id"], p.get("ovr"), p.get("rarity"), p.get("source"), p.get("face_stats"), {k: p["attributes"].get(k) for k in ("acceleration", "sprint_speed", "dribbling", "agility")})
players = cli._load_players(["data/ea_players.json", "data/spesialkort.json"])
for p in players:
    if "Bisiwu" in p.name:
        w("used", p.name, p.id, p.ovr, p.rarity, p.source, p.face_stats, {k: p.attributes.get(k) for k in ("acceleration", "sprint_speed")})
# how often do face stats and attributes disagree (PAC from attributes vs shown PAC)?
cfg = load_config()
rules = json.load(open("config/evolab.json"))["rules"]
bad = collections.Counter(); ex = []
for p in players:
    fs = p.face_stats or {}
    if not fs.get("pac") or p.position == "GK": continue
    pv = face_value(p.attributes, "pace", rules)
    if pv is None: continue
    if abs(pv - fs["pac"]) > 1:
        bad[(p.source, p.rarity if "Rare" in (p.rarity or "") or "Common" in (p.rarity or "") else "special")] += 1
        if len(ex) < 25: ex.append((p.name, p.id, p.rarity, p.source, fs.get("pac"), pv, p.attributes.get("acceleration"), p.attributes.get("sprint_speed")))
w("players", len(players), "pace mismatch", sum(bad.values()), dict(bad))
for e in ex: w("  ", e)
# compare EA vs FIFA Rosters base attributes for the same id
eam = {str(p["id"]): p for p in ea}
diff = 0; dex = []
for p in sp:
    if p.get("source") and str(p.get("id")) in eam and "Rare" in (p.get("rarity") or "") or "Common" in (p.get("rarity") or ""):
        q = eam.get(str(p.get("id")))
        if not q: continue
        dd = {k: (q["attributes"].get(k), p["attributes"].get(k)) for k in q["attributes"] if q["attributes"].get(k) != p["attributes"].get(k)}
        if dd:
            diff += 1
            if len(dex) < 10: dex.append((p["name"], p["id"], p.get("source"), list(dd.items())[:6]))
w("base cards in both with different attributes:", diff)
for e in dex: w("  ", e)
log.close()
