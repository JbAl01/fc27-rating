import urllib.request, urllib.error, time, re
from fcrating import net
out = []
def log(*a): out.append(" ".join(str(x) for x in a))
UA = {"User-Agent": "fc27-rating/0.2 (personlig bruk)", "Accept": "image/webp,image/png,image/*"}
f = net.PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2)
pages = {"mbappe": "https://www.fut.gg/players/231747/27-231747/", "pele": "https://www.fut.gg/players/237067/27-67345931/",
         "promo": "https://www.fut.gg/players/227203/27-67336067/", "silver": "https://www.fut.gg/players/264938/27-264938/",
         "bronze": "https://www.fut.gg/players/269875/27-269875/"}
n = 0
for key, u in pages.items():
    try:
        h = f.get(u)
    except Exception as e:
        log("page fail", key, repr(e)); continue
    card = u.rstrip("/").split("/27-")[-1]
    log("==", key, card)
    kinds = ["player-item", "player-item-card", "player-item-simple-card", "futgg-player-item-card"]
    for k in kinds:
        m = re.search(r'https://game-assets\.fut\.gg/cdn-cgi/image/[^"\'\s\\<>]*?/2027/%s/27-%s\.[0-9a-f]+\.webp' % (k, card), h)
        if m:
            log(k, m.group(0)); 
            if key in ("mbappe", "pele"):
                try:
                    b = urllib.request.urlopen(urllib.request.Request(m.group(0).replace("width=300", "width=400"), headers=UA), timeout=20).read()
                    open(f"/tmp/img_{key}_{k}.webp", "wb").write(b)
                except Exception as e: log("dl fail", k, repr(e))
    # rarity picture right after the player-item picture
    i = h.find("/player-item/27-%s." % card)
    m = re.search(r'https://game-assets\.fut\.gg/cdn-cgi/image/[^"\'\s\\<>]*?/2027/rarities-level-\d-large/\d+\.[0-9a-f]+\.png', h[i:]) if i >= 0 else None
    if m:
        log("rarity", m.group(0))
        try:
            b = urllib.request.urlopen(urllib.request.Request(m.group(0).replace("width=300", "width=400"), headers=UA), timeout=20).read()
            open(f"/tmp/img_{key}_rarity.png", "wb").write(b)
        except Exception as e: log("dl fail rarity", repr(e))
try:
    b = urllib.request.urlopen(urllib.request.Request("https://ratings-images-prod.pulse.ea.com/FC25/full/player-portraits/p231747.png?padding=0.7", headers=UA), timeout=20).read()
    open("/tmp/img_ea_avatar.png", "wb").write(b)
except Exception as e: log("avatar fail", repr(e))
open("/tmp/probe_card.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
