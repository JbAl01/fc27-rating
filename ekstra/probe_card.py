import json, collections, glob, os
from fcrating.evolab import face_value
log = open("/tmp/an.txt", "w")
def w(*a): log.write(" ".join(str(x) for x in a) + "\n"); log.flush()
w(os.listdir("data/cache/fifarosters"))
def load(f):
    d = json.load(open(f)); return d if isinstance(d, list) else d.get("players", [])
ea = {str(p["id"]): p for p in load("data/ea_players.json")}
sp = load("data/spesialkort.json")
rules = json.load(open("config/evolab.json"))["rules"]
F = {"pac": "pace", "sho": "shooting", "pas": "passing", "dri": "dribbling", "def": "defending", "phy": "physical"}
def consist(p):
    a = p["attributes"]; fs = p.get("face_stats") or {}
    out = {}
    for k, n in F.items():
        if n not in rules["face"] or fs.get(k) is None: continue
        v = face_value(a, n, rules)
        if v is not None: out[k] = v - fs[k]
    return out
for name, src in (("EA", list(ea.values())), ("FRbase", [p for p in sp if p.get("source") == "FIFA Rosters (FC 27-basekort)"]), ("FRspecial", [p for p in sp if p.get("source") == "FIFA Rosters"])):
    c = collections.Counter(); n = 0
    for p in src:
        if p.get("position") == "GK": continue
        d = consist(p); n += 1
        for k, v in d.items():
            if abs(v) > 1: c[k] += 1
    w(name, "cards", n, "face off by >1:", dict(c))
# estimated flag
fb = [p for p in sp if p.get("source") == "FIFA Rosters (FC 27-basekort)"]
w("FRbase estimated", sum(1 for p in fb if p.get("estimated")), "of", len(fb))
for nm in ("Harry Kane", "Jesse Eugen Bisiwu"):
    for p in fb:
        if p["name"] == nm:
            q = ea.get(str(p["id"]))
            w(nm, "estimated", p.get("estimated"), "notes", p.get("notes"))
            w("  FR", sorted(p["attributes"].items()))
            w("  EA", sorted(q["attributes"].items()) if q else None)
log.close()
