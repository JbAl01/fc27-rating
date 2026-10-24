import copy, json
from fcrating.cli import _load_players, _add_usage, _owner_tests, _rep_frames
from fcrating.model import load_config, rate, rank_by_position
def run(cfg, label):
    players = _load_players(["data/ea_players.json", "data/spesialkort.json"])
    _rep_frames(cfg, players)
    res = [rate(p, cfg) for p in players]
    rank_by_position(res, cfg)
    print(f"\n== {label}")
    _add_usage(res)
    _owner_tests(res)
    for g in ("ST", "W", "CAM", "FB", "CB", "GK"):
        rows = sorted([r for r in res if r.get("position_group") == g and r.get("status") != "lekket"], key=lambda r: -r["by_group"][g]["igr"])
        seen, out = set(), []
        for r in rows:
            if r["name"] in seen: continue
            seen.add(r["name"]); out.append(f"{r['name']} {r['by_group'][g]['igr']}")
            if len(out) >= 8: break
        print(" ", g, ", ".join(out))
new = load_config()
old = copy.deepcopy(new)
old["playstyles"] = json.load(open("ekstra/ps_old.json"))
run(old, "før")
run(new, "etter")
