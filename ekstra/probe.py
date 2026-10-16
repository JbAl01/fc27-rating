import json, gzip, urllib.request, time
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
        if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
        return json.loads(b)
d = get("https://www.fut.gg/api/fut/players/v2/27/")
print("top keys", list(d.keys()), {k: v for k, v in d.items() if k != "data"})
print("n items", len(d["data"]))
it = d["data"][0]; print("item keys", sorted(it.keys()))
print(json.dumps({k: it[k] for k in it if k not in ("cardImageUrl",)}, ensure_ascii=False)[:2500])
for q in ["?page=2", "?page=500", "?search=cambiaghi&page=1", "?name=cambiaghi", "?q=cambiaghi"]:
    try:
        x = get("https://www.fut.gg/api/fut/players/v2/27/" + q)
        print(q, {k: v for k, v in x.items() if k != "data"}, len(x["data"]), [ (i.get("commonName") or i.get("cardName"), i.get("rarityName"), i.get("overall")) for i in x["data"][:4]])
    except Exception as e:
        print(q, "ERR", e)
    time.sleep(1)
x = get("https://www.fut.gg/api/fut/player-item-definitions/27/268703/")
print(json.dumps(x, ensure_ascii=False)[:6000])
for u in ["https://www.fut.gg/api/fut/playstyles/", "https://www.fut.gg/api/fut/playstyles/27/", "https://www.fut.gg/api/fut/metadata/27/"]:
    try:
        y = get(u); print(u, json.dumps(y)[:1500])
    except Exception as e:
        print(u, "ERR", e)
