import urllib.request, urllib.error, time
out = []
def log(*a): out.append(" ".join(str(x) for x in a))
UA = {"User-Agent": "fc27-rating/0.2 (personlig bruk)", "Accept": "image/webp,image/png,image/*"}
H = "game-assets.fut.gg/cdn-cgi/image/quality=85,format=auto,width=300/2027"
URLS = [
 "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/en/231747.png?width=265",
 "https://ratings-images-prod.pulse.ea.com/FC27/full/player-shields/en/231747.png?width=265",
 "https://ratings-images-prod.pulse.ea.com/FC26/full/player-shields/en/231747.png?width=265",
 "https://ratings-images-prod.pulse.ea.com/FC27/full/player-shields/en/67345931.png?width=265",
 "https://ratings-images-prod.pulse.ea.com/FC27/full/player-shields/en/100890499.png?width=265",
 "https://ratings-images-prod.pulse.ea.com/FC27/full/player-shields/en/67336067.png?width=265",
 f"https://{H}/futgg-player-item-card/27-231747.webp",
 f"https://{H}/player-item-card/27-231747.webp",
 f"https://{H}/player-item-card/27-67336067.webp",
 f"https://{H}/futgg-player-item-card/27-67336067.webp",
 "https://game-assets.fut.gg/2027/futgg-player-item-card/27-231747.webp",
 "https://game-assets.fut.gg/cdn-cgi/image/quality=85,format=auto,width=300/2027/futgg-player-item-card/27-231747.37dd54fdcfca9c59db34466e2dc0ef50f16417dcf5c64aaa7fdd8bba85f5b7a7.webp",
]
for u in URLS:
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20)
        b = r.read()
        log("OK", r.status, r.headers.get("content-type"), len(b), u)
        if u == URLS[0]: open("/tmp/ea_shield.png", "wb").write(b)
    except urllib.error.HTTPError as e:
        log("HTTP", e.code, u)
    except Exception as e:
        log("ERR", repr(e)[:80], u)
    time.sleep(1.5)
open("/tmp/probe_card.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
