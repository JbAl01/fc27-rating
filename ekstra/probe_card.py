import json, re
from fcrating import net
from fcrating.sources import futgg
log = open("/tmp/an.txt", "w")
def w(*a):
    log.write(" ".join(str(x) for x in a) + "\n"); log.flush()
try:
    ic = json.load(open("data/cache/futgg/ikoner.json"))
    w("ikoner.json", len(ic), sorted(ic)[:60])
    for k in list(ic)[:3]:
        w(" ", k, json.dumps(ic[k])[:1500])
except Exception as e:
    w("no ikoner", repr(e))
f = net.PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2)
h = f.get("https://www.fut.gg/players/252145/27-252145/")
open("/tmp/mendes.html", "w").write(h)
n = 0
for m in re.finditer(r'<svg[^>]*height="4\d"[^>]*>.*?</svg>', h, re.S):
    w("SVG", h[max(0, m.start()-300):m.start()].replace("\n", " ")[-300:])
    w("   ", m.group(0)[:4000])
    n += 1
    if n >= 3: break
w("parse_icons", {k: (v["vb"], len(v["d"]), [len(x) for x in v["d"]]) for k, v in futgg.parse_icons(h).items()})
