import json, re
from fcrating import net
from fcrating.sources import ea_ratings, futgg
out = []
def log(*a): out.append(" ".join(str(x) for x in a))
UA = "fc27-rating/0.2 (personlig bruk)"
# 1) EA ratings page: first item, all keys, any image-like or league fields
try:
    html = ea_ratings._get_html("https://www.ea.com/games/ea-sports-fc/ratings?page=1", "Mozilla/5.0 (compatible; fc27-rating/0.3; personlig bruk)")
    items = ea_ratings._dig(ea_ratings.next_data(html), "props.pageProps.ratingDetails.items")
    log("EA items", len(items))
    it = items[0]
    log("EA top keys", sorted(it.keys()))
    for k in it:
        v = it[k]
        if isinstance(v, dict) and ("league" in k.lower() or "team" in k.lower() or "nation" in k.lower()):
            log("EA obj", k, json.dumps(v)[:400])
    for k in ("preferredFoot", "foot", "weakFootAbility", "skillMoves", "leagueName", "league"):
        log("EA", k, json.dumps(it.get(k))[:200])
    n_league = sum(1 for x in items if isinstance(x.get("league"), dict) and x["league"].get("imageUrl"))
    log("items with league.imageUrl", n_league, "of", len(items))
    log("any key with league:", sorted({k for x in items for k in x if "league" in k.lower()}))
except Exception as e:
    log("EA fail", repr(e))
# 2) FUT.GG: own parser on real pages
f = net.PoliteFetcher(user_agent=UA, delay_seconds=2)
pages = {"mbappe": "https://www.fut.gg/players/231747/27-231747/", "pele": "https://www.fut.gg/players/237067/27-67345931/",
         "promo": "https://www.fut.gg/players/227203/27-67336067/"}
for key, u in pages.items():
    try:
        h = f.get(u)
    except Exception as e:
        log("page fail", key, repr(e)); continue
    card = u.rstrip("/").split("/27-")[-1]
    rec = futgg.parse_card_page(h, card)
    log("==", key, card, "rec img:", (rec or {}).get("img"), "face:", (rec or {}).get("face"))
    folders = sorted(set(re.findall(r"https://game-assets\.fut\.gg/cdn-cgi/image/[^/]*/(\d{4}/[a-z0-9\-]+)/", h)))
    log("folders", folders)
    for fo in folders:
        if any(w in fo for w in ("league", "nation", "club", "badge", "flag")):
            m = re.search(r"https://game-assets\.fut\.gg/cdn-cgi/image/[^\"'\s\\<>]*/%s/[^\"'\s\\<>]+" % re.escape(fo), h)
            log("  sample", fo, m.group(0) if m else None)
    log("foot text:", re.findall(r"(?:Preferred Foot|Foot)[^<]{0,40}<[^>]*>[^<]{0,20}", h)[:2])
open("/tmp/probe_card.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
