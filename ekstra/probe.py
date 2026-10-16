import json, collections
from fcrating.sources import local
ea = local.load_any("data/ea_players.json")
n = len(ea); withps = sum(1 for p in ea if p.playstyles or p.playstyles_plus)
print("EA players", n, "with PS", withps, "complete-flag false", sum(1 for p in ea if not p.playstyles_complete))
hi = [p for p in ea if (p.ovr or 0) >= 80]
print("EA ovr>=80", len(hi), "with PS", sum(1 for p in hi if p.playstyles or p.playstyles_plus))
cnt = collections.Counter(len(p.playstyles) + len(p.playstyles_plus) for p in hi); print("PS count dist ovr>=80", sorted(cnt.items()))
print("heights missing", sum(1 for p in ea if not p.height_cm), "league set", sum(1 for p in ea if p.league))
for p in ea:
    if "Cambiaghi" in p.name or "Bellingham" in p.name:
        print("EA", p.name, p.id, p.ovr, p.position, p.playstyles, p.playstyles_plus, p.playstyles_complete, p.height_cm, p.league)
sp = local.load_any("data/spesialkort.json")
for p in sp:
    if "Cambiaghi" in p.name:
        print("SP", p.name, p.rarity, p.ovr, p.source, p.playstyles, p.playstyles_plus, p.playstyles_complete, p.base_id, p.height_cm)
raw = json.load(open("data/ea_players.json"))
print("raw sample keys", list((raw.get("players") or raw)[0].keys()))
