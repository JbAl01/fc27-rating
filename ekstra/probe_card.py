import collections, random, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from fcrating import cli
log = open("/tmp/an.txt", "w")
def w(*a):
    log.write(" ".join(str(x) for x in a) + "\n"); log.flush()
players = cli._load_players(["data/ea_players.json", "data/spesialkort.json"])
w("cards", len(players))
host = collections.Counter((p.image or "NONE").split("/")[2] if p.image else "NONE" for p in players)
w("image hosts", dict(host))
fb = [p for p in players if p.image and "futbin" in p.image]
random.seed(2)
sample = random.sample(fb, min(400, len(fb)))
def st(p):
    try:
        r = urllib.request.urlopen(urllib.request.Request(p.image, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}), timeout=20)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return repr(e)[:40]
with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(st, sample))
w("futbin sample", len(sample), collections.Counter(res))
for p, r in zip(sample, res):
    if r != 200:
        w("  miss", p.name, p.id, p.base_id, p.ovr, p.rarity, p.image)
for n in ("Dermane Karim", "Nuno Mendes"):
    for p in players:
        if p.name == n:
            w(n, p.id, p.base_id, p.rarity, p.image)
