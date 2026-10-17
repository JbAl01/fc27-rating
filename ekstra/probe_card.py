import collections, json, re, urllib.request, urllib.error
from fcrating import net
from fcrating.sources import ea_ratings

out = []
def log(*a):
    s = " ".join(str(x) for x in a); out.append(s); print(s, flush=True)

def status(u, ua="Mozilla/5.0 (compatible; fc27-rating; personlig bruk)"):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": ua}), timeout=20)
        b = r.read(64)
        return r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length")
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except Exception as e:
        return repr(e)[:80], None, None

# 1) cached EA list: which image urls do players have, and do they load?
ps = json.load(open("data/ea_players.json"))
ps = ps if isinstance(ps, list) else ps.get("players", [])
log("players", len(ps))
pat = collections.Counter()
for p in ps:
    im = p.get("image") or ""
    pat[re.sub(r"\d+", "N", im)[:120] if im else "NONE"] += 1
for k, v in pat.most_common(10):
    log("  img pattern", v, k)
low = [p for p in ps if p.get("ovr", 99) < 70]
mid = [p for p in ps if 70 <= p.get("ovr", 0) < 76]
import random
random.seed(1)
sample = random.sample(low, 8) + random.sample(mid, 6) + [p for p in ps if "Karim" in p["name"]][:3]
ids = []
for p in sample:
    im = p.get("image")
    log("--", p["name"], p["id"], p["ovr"], im, status(im) if im else "")
    ids.append(p["id"])

# 2) candidate predictable urls
cands = [
    "https://ratings-images-prod.pulse.ea.com/FC27/full/player-portraits/p{id}.png",
    "https://ratings-images-prod.pulse.ea.com/FC27/full/player-portraits/{id}.png",
    "https://ratings-images-prod.pulse.ea.com/FC26/full/player-portraits/p{id}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-portraits/p{id}.png",
    "https://drop-assets.ea.com/images/player-portraits/fc27/{id}.png",
    "https://cdn.futbin.com/content/fifa27/img/players/{id}.png",
    "https://cdn.futbin.com/content/fifa27/img/players/p{id}.png",
    "https://cdn.futbin.com/content/fifa26/img/players/{id}.png",
    "https://cdn3.futbin.com/content/fifa27/img/players/{id}.png",
]
for c in cands:
    res = [status(c.format(id=i))[0] for i in ids]
    log("cand", c, res)

# 3) EA ratings page with low-rated players: every url-ish string of one item
try:
    ua = "Mozilla/5.0 (compatible; fc27-rating/0.3; personlig bruk)"
    for page in (150, 190):
        html = ea_ratings._get_html(f"https://www.ea.com/games/ea-sports-fc/ratings?page={page}", ua)
        items = ea_ratings._dig(ea_ratings.next_data(html), "props.pageProps.ratingDetails.items") or []
        log("EA page", page, len(items))
        for it in items[:3]:
            urls = [(k, v) for k, v in ea_ratings._walk(it) if isinstance(v, str) and v.startswith("http")]
            log("  item", it.get("firstName"), it.get("lastName"), it.get("overallRating"), it.get("id"))
            for k, v in urls:
                log("    ", k, v, status(v)[0])
except Exception as e:
    log("EA fail", repr(e))

# 4) FUT.GG list pages: faces per page?
f = net.PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2)
for u in ["https://www.fut.gg/players/?page=200", "https://www.fut.gg/players/?overall__lte=65", "https://www.fut.gg/players/"]:
    try:
        h = f.get(u)
        faces = re.findall(r"https://game-assets\.fut\.gg/cdn-cgi/image/[^\"'\s\\<>]*/2027/player-item/27-(\d+)\.[0-9a-f]+\.png", h)
        links = re.findall(r"/players/(\d+)/27-(\d+)/", h)
        log("FUTGG list", u, len(h), "faces", len(faces), len(set(faces)), "links", len(set(links)), faces[:3], list(set(links))[:3])
    except Exception as e:
        log("FUTGG list fail", u, repr(e)[:200])
# 5) base page for a low player: face there?
for i in ids[:3]:
    try:
        h = f.get(f"https://www.fut.gg/players/{i}/27-{i}/")
        m = re.findall(r"https://game-assets\.fut\.gg/cdn-cgi/image/[^\"'\s\\<>]*/2027/player-item/[^\"'\s\\<>]+", h)
        log("FUTGG base", i, len(h), m[:2])
    except Exception as e:
        log("FUTGG base fail", i, repr(e)[:200])
open("/tmp/an.txt", "w", encoding="utf-8").write("\n".join(out))
