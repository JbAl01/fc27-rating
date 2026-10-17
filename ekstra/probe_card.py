import hashlib, json, os, urllib.request
os.makedirs("/tmp/img", exist_ok=True)
log = open("/tmp/an.txt", "w")
for u in json.load(open("ekstra/urls.json")):
    name = hashlib.md5(u.encode()).hexdigest()[:12]
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/webp,image/png,*/*"}), timeout=30)
        b = r.read()
        ext = {"image/webp": "webp", "image/png": "png", "image/avif": "avif", "image/jpeg": "jpg"}.get(r.headers.get("Content-Type"), "bin")
        open(f"/tmp/img/{name}.{ext}", "wb").write(b)
        log.write(f"{name}.{ext} {len(b)} {u}\n")
    except Exception as e:
        log.write(f"FAIL {u} {e!r}\n")
log.close()
