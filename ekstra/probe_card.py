import os, re, urllib.request
from fcrating import net
os.makedirs("/tmp/pages", exist_ok=True)
log = open("/tmp/an.txt", "w")
def get(u, name):
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
        open("/tmp/pages/" + name, "wb").write(b); log.write(f"{name} {len(b)}\n")
        return b.decode("utf-8", "replace")
    except Exception as e:
        log.write(f"{name} fail {e!r}\n"); return ""
h = get("https://jbal01.github.io/fc27-rating/evolab.html", "evolab.html")
for js in sorted(set(re.findall(r'src="(evolab-data-\d+\.js[^"]*)"', h))):
    get("https://jbal01.github.io/fc27-rating/" + js.split("?")[0], js.split("?")[0])
f = net.PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2)
for name, u in {"intro.html": "https://www.fut.gg/evolutions/2492-intro-to-repeatable-evolutions/",
                "futnext_intro.html": "https://www.futnext.com/evolutions/intro-to-repeatable-evolutions/2697"}.items():
    try:
        x = f.get(u); open("/tmp/pages/" + name, "w").write(x); log.write(f"{name} {len(x)}\n")
    except Exception as e:
        log.write(f"{name} fail {e!r}\n")
log.close()
