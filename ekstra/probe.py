"""Probe 2: where the FC 27 player list with alternatePositions sits in EA's ratings page."""
import json, re, gzip, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (fc27-rating probe)", "Accept-Language": "en"}
def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")
def walk(o, path=""):
    if isinstance(o, dict):
        if isinstance(o.get("alternatePositions"), list):
            yield path, o
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
def page(url):
    html = get(url)
    data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
    return data
for url in ["https://www.ea.com/games/ea-sports-fc/ratings", "https://www.ea.com/games/ea-sports-fc/ratings?page=2",
            "https://www.ea.com/games/ea-sports-fc/ratings?page=150"]:
    print("=" * 20, url)
    try:
        data = page(url)
    except Exception as e:
        print("ERR", e); continue
    pp = data["props"]["pageProps"]
    print("pageProps keys", list(pp.keys()))
    for k, v in pp.items():
        if isinstance(v, dict):
            print(" ", k, "->", list(v.keys())[:25])
    items = list(walk(data))
    paths = {}
    for p, it in items:
        base = re.sub(r"\[\d+\]", "[]", p)
        paths[base] = paths.get(base, 0) + 1
    print("paths with alternatePositions list:", paths)
    for p, it in items[:2]:
        print(" path", p)
        print(" keys", sorted(it.keys()))
        print(" sample", json.dumps({k: it.get(k) for k in ("id", "firstName", "lastName", "commonName", "overallRating", "position", "alternatePositions", "avatarUrl", "rank")}, ensure_ascii=False)[:700])
    ids = [it.get("id") for _, it in items]
    print(" ids", ids[:5], "...", len(ids))
    for _, it in items:
        if "Vetlesen" in json.dumps(it, ensure_ascii=False):
            print(" VETLESEN", json.dumps({k: it.get(k) for k in ("id", "overallRating", "position", "alternatePositions")}, ensure_ascii=False))
for q in ["https://www.ea.com/games/ea-sports-fc/ratings?search=Vetlesen", "https://www.ea.com/games/ea-sports-fc/ratings?team=231"]:
    print("=" * 20, q)
    try:
        data = page(q)
        for _, it in walk(data):
            if "etlesen" in json.dumps(it, ensure_ascii=False):
                print(" VETLESEN", json.dumps({k: it.get(k) for k in ("id", "overallRating", "position", "alternatePositions", "avatarUrl")}, ensure_ascii=False))
        print(" n items", len(list(walk(data))))
    except Exception as e:
        print("ERR", e)
