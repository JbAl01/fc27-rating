import copy
from fcrating.net import PoliteFetcher
from fcrating.sources import futgg, fifarosters as fr, local
from fcrating import specials
from fcrating.model import load_config, rate
f = PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2.0)
print("robots api", f.allowed("https://www.fut.gg/api/fut/player-item-definitions/27/1/"), "players", f.allowed("https://www.fut.gg/players/268703/27-50600351/"))
cache = fr.FifaRostersCache("data/cache/fifarosters")
ents = sorted(specials.unique_entries(cache), key=lambda t: -t[1]["ovr"])
todo = [(str(e.get("player_id") or ""), fid) for fid, e in ents if not fr.is_base_version(e["version"])]
camb = [t for t in todo if t[1] == "50600351"]
print("specials", len(todo))
fg = futgg.FutggCache("/tmp/fg")
print("read", futgg.fetch_cards(f, fg, camb + todo[:40], 41))
cfg = load_config()
sp = {p.id: p for p in local.load_any("data/spesialkort.json")}
diffs = []
for cid, rec in fg.cards.items():
    p = sp.get(cid)
    if not p: print("no card", cid, rec); continue
    if rec.get("missing"): print("MISSING", p.name, p.rarity, cid); continue
    before = rate(p, cfg); q = copy.deepcopy(p); futgg.apply([q], {cid: rec}); after = rate(q, cfg)
    g = before.get("position_group") or before["best_group"]
    b, a = before["by_group"][g]["igr"], after["by_group"][g]["igr"]
    diffs.append(a - b)
    print(f"{p.name:24s} {p.rarity[:28]:28s} {p.ovr} {g:4s} PS før {len(p.playstyles)}+{len(p.playstyles_plus)} etter {len(q.playstyles)}+{len(q.playstyles_plus)}  IGR {b:.1f} -> {a:.1f}  h={rec.get('height')}  ny: {sorted(set(q.playstyles+[x+'+' for x in q.playstyles_plus]) - set(p.playstyles+[x+'+' for x in p.playstyles_plus]))}")
if diffs:
    print("snitt endring", round(sum(diffs)/len(diffs), 2), "maks", round(max(diffs), 2), "min", round(min(diffs), 2), "endret", sum(1 for d in diffs if abs(d) > 0.05), "av", len(diffs))
