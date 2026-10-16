import json, re, sys
from fcrating import net
from fcrating.sources import ea_ratings
out = []
def log(*a):
    out.append(" ".join(str(x) for x in a))
f = net.PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2)
# EA: every key of the first item, and every string that looks like a URL
try:
    h = f.get("https://www.ea.com/games/ea-sports-fc/ratings?page=1")
    d = ea_ratings.next_data(h)
    it = d["props"]["pageProps"]["ratingDetails"]["items"][0]
    log("EA keys:", sorted(it.keys()))
    def walk(o, p=""):
        if isinstance(o, dict):
            for k, v in o.items(): walk(v, p + "." + k)
        elif isinstance(o, list):
            for i, v in enumerate(o[:3]): walk(v, p + f"[{i}]")
        elif isinstance(o, str) and ("http" in o or o.endswith((".png", ".webp", ".jpg"))):
            log("EA url", p, o)
    walk(it)
except Exception as e:
    log("EA fail", repr(e))
URLS = ["https://www.fut.gg/players/231747/27-231747/", "https://www.fut.gg/players/237067/27-67345931/",
        "https://www.fut.gg/players/227203/27-100890499/", "https://www.fut.gg/players/227203/27-67336067/",
        "https://www.fut.gg/players/264938/27-264938/"]
for u in URLS:
    try:
        h = f.get(u)
        log("\n==", u, len(h))
        for m in re.finditer(r'<meta[^>]+(?:og:image|twitter:image)[^>]*>', h): log(m.group(0)[:300])
        seen = set()
        for m in re.finditer(r'https?://[^"\'\s\\<>)]+\.(?:png|webp|jpg|jpeg)[^"\'\s\\<>)]*', h):
            x = m.group(0)
            if x in seen: continue
            seen.add(x); log("img", x[:260])
            if len(seen) > 40: break
    except Exception as e:
        log("FUTGG fail", u, repr(e))
open("/tmp/probe_card.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out)[:3000])
