"""One-off probe run in GitHub Actions: where can FC 27 alternative positions come from, and what does
the real data say about one card. Prints only; changes nothing."""
import json, re, sys, gzip, urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (fc27-rating probe)", "Accept-Language": "en"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return r.status, raw.decode("utf-8", "replace")

def find_items(obj, path="", out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        if "alternatePositions" in obj or ("overallRating" in obj and ("firstName" in obj or "lastName" in obj)):
            out.append((path, obj))
        for k, v in obj.items():
            find_items(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3000]):
            find_items(v, f"{path}[{i}]", out)
    return out

def probe_page(url):
    print("=" * 30, url)
    try:
        st, html = get(url)
    except Exception as e:
        print("ERR", e); return
    print("status", st, "len", len(html))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    print("__NEXT_DATA__:", bool(m))
    for k in ("alternatePositions", "drop-api", "overallRating", "FC27", "fc27", "self.__next_f"):
        print(f"  contains {k!r}:", html.count(k))
    for api in sorted(set(re.findall(r'https://drop-api[^"\'\s\\]+', html)))[:10]:
        print("  api url:", api)
    if m:
        data = json.loads(m.group(1))
        items = find_items(data)
        print("items found:", len(items))
        for path, it in items[:3]:
            print(" path", path)
            print(" keys", sorted(it.keys())[:40])
            print(" sample", json.dumps({k: it.get(k) for k in ("id", "firstName", "lastName", "commonName", "overallRating", "position", "alternatePositions", "avatarUrl")}, ensure_ascii=False)[:600])
    else:
        # app router: data in self.__next_f.push chunks
        chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
        print("next_f chunks:", len(chunks))
        joined = "".join(chunks)
        i = joined.find("alternatePositions")
        print("  alternatePositions at", i, joined[max(0, i - 400):i + 400] if i >= 0 else "")

for url in ["https://www.ea.com/games/ea-sports-fc/ratings",
            "https://www.ea.com/games/ea-sports-fc/ratings?page=2",
            "https://www.ea.com/games/ea-sports-fc/ratings/teams-ratings/club-brugge-kv/231"]:
    probe_page(url)

for url in ["https://drop-api.ea.com/rating/ea-sports-fc?locale=en&limit=1&offset=0",
            "https://drop-api.ea.com/rating/ea-sports-fc-27?locale=en&limit=1&offset=0",
            "https://drop-api.ea.com/rating/fc-27?locale=en&limit=1&offset=0",
            "https://drop-api.ea.com/rating/ea-sports-fc?locale=en&limit=1&offset=0&gameId=27"]:
    print("=" * 30, url)
    try:
        st, body = get(url)
        print("status", st, body[:400].replace("\n", " "))
    except Exception as e:
        print("ERR", e)

print("=" * 30, "real data: Vetlesen")
for f in ("data/spesialkort.json", "data/ea_players.json"):
    p = Path(f)
    if not p.exists():
        print(f, "missing"); continue
    data = json.load(open(p, encoding="utf-8"))
    items = data.get("players", data) if isinstance(data, dict) else data
    for c in items:
        if "vetlesen" in json.dumps(c.get("name", "")).lower():
            print(f, json.dumps({k: c.get(k) for k in ("name", "rarity", "ovr", "position", "alt_positions", "source", "card_id", "url", "playstyles", "roles", "weak_foot", "skill_moves")}, ensure_ascii=False)[:900])
