import hashlib, os, urllib.request, urllib.error
os.makedirs("/tmp/img", exist_ok=True)
log = open("/tmp/an.txt", "w")
ids = ["87528", "74689", "79083", "77636", "273458", "277072", "231747", "999999999", "1", "50563395", "67345931"]
for i in ids:
    for tpl in ("https://cdn.futbin.com/content/fifa27/img/players/{id}.png", "https://cdn.futbin.com/content/fifa27/img/players/p{id}.png"):
        u = tpl.format(id=i)
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1", "Referer": "https://jbal01.github.io/"}), timeout=20)
            b = r.read()
            h = dict(r.headers)
            log.write(f"{u} {r.status} {len(b)} {hashlib.md5(b).hexdigest()[:10]} {h.get('Content-Type')} {h.get('Cache-Control')} {h.get('Access-Control-Allow-Origin')} {h.get('Last-Modified')}\n")
            if "/p" not in u.rsplit("/", 1)[1]:
                open(f"/tmp/img/{i}.png", "wb").write(b)
        except urllib.error.HTTPError as e:
            log.write(f"{u} {e.code}\n")
        except Exception as e:
            log.write(f"{u} {e!r}\n")
log.close()
