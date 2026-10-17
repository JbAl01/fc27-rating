import json, collections
from fcrating import cli, evolab
from fcrating.model import load_config
log = open("/tmp/an.txt", "w")
def w(*a): log.write(" ".join(str(x) for x in a) + "\n"); log.flush()
players = cli._load_players(["data/ea_players.json", "data/spesialkort.json"])
lab = json.load(open("config/evolab.json")); rules = lab["rules"]
F = {"pac": "pace", "sho": "shooting", "pas": "passing", "dri": "dribbling", "def": "defending", "phy": "physical"}
c = collections.Counter(); n = 0
for p in players:
    if p.position == "GK" or not p.face_stats: continue
    n += 1
    for k, nm in F.items():
        if nm in rules["face"] and p.face_stats.get(k) is not None:
            v = evolab.face_value(p.attributes, nm, rules)
            if v is not None and abs(v - p.face_stats[k]) > 1: c[(p.source, k)] += 1
w("after fix: outfield cards", n, "mismatch >1:", dict(c))
live, _ = evolab.active_live(lab)
cfg = load_config()
for nm in ("Jesse Eugen Bisiwu",):
    for p in players:
        if p.name == nm:
            st = evolab.state_from(p)
            w(nm, p.rarity, p.ovr, "PAC", evolab.face_value(p.attributes, "pace", rules), {k: p.attributes.get(k) for k in ("acceleration", "sprint_speed")})
            for e in live:
                why = evolab.check(e, st, rules)
                if not why or why[0] != "pos": w("  ", e["key"], why)
            ev = evolab.Evaluator(p, evolab.card_group(p) or "ST", cfg, rules)
            plan = evolab.plan_live(p, st, live, ev, rules)
            w("  plan keys", list(plan.keys()))
            w("  plan", json.dumps({k: v for k, v in plan.items() if k != "_state"}, default=str, ensure_ascii=False)[:1500])
# any plan in sample with the same evo twice?
import random
random.seed(3)
samp = random.sample([p for p in players if p.position != "GK"], 150)
twice = 0
for p in samp:
    st = evolab.state_from(p); ev = evolab.Evaluator(p, evolab.card_group(p) or "ST", cfg, rules)
    plan = evolab.plan_live(p, st, live, ev, rules)
    keys = [x[0] if isinstance(x, (list, tuple)) else (x.get("key") if isinstance(x, dict) else x) for x in plan.get("steps", plan.get("chain", []))]
    if len(keys) != len(set(map(str, keys))): twice += 1
w("sample plans with an evo twice:", twice, "of", len(samp))
log.close()
