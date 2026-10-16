import urllib.request
from fcrating.net import PoliteFetcher
from fcrating.sources import futgg, fifarosters as fr
from fcrating import specials
for ua in ["fc27-rating/0.2 (personlig bruk)", "Mozilla/5.0 (compatible; fc27-rating/0.3; personlig bruk)"]:
    f = PoliteFetcher(user_agent=ua, delay_seconds=0.8)
    print("UA", ua, "robots allow api:", f.allowed("https://www.fut.gg/api/fut/player-item-definitions/27/268703/"))
    try:
        print("  get ok", len(f.get("https://www.fut.gg/api/fut/player-item-definitions/27/268703/")))
    except Exception as e:
        print("  get ERR", e)
req = urllib.request.Request("https://www.fut.gg/robots.txt", headers={"User-Agent": "Mozilla/5.0"})
print(urllib.request.urlopen(req, timeout=30).read().decode()[:1500])
cache = fr.FifaRostersCache("data/cache/fifarosters")
ids = [fid for fid, e in specials.unique_entries(cache) if "Cambiaghi" in e["name"] or "Bellingham" in e["name"]]
print("ids", [(fid, cache.entries[fid]["version"], cache.entries[fid]["ovr"]) for fid in ids])
fg = futgg.FutggCache("/tmp/fg")
f = PoliteFetcher(user_agent="Mozilla/5.0 (compatible; fc27-rating/0.3; personlig bruk)", delay_seconds=0.8)
print("fetched", futgg.fetch_items(f, fg, ids + ["268703"], 20))
for k, v in fg.cards.items(): print(k, v)
