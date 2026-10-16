import re, gzip, urllib.request
UA = "Mozilla/5.0 (compatible; fc27-rating/0.3; personlig bruk)"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=40) as r:
        b = r.read(); fin = r.geturl()
        if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
        return fin, b.decode("utf-8", "replace")
for url in ["https://www.fut.gg/players/268703-nicolo-cambiaghi/27-50600351/", "https://www.fut.gg/players/268703/27-50600351/",
            "https://www.fut.gg/players/252371-jude-bellingham/27-252371/"]:
    try:
        fin, h = get(url)
    except Exception as e:
        print(url, "ERR", e); continue
    print("=====", url, "->", fin, len(h))
    for m in re.finditer(r'<div(?: class="([^"]*)")? title="([^"]+)"><svg[^>]*height="(\d+)"[^>]*>(.{0,120})', h):
        print("  ", m.start(), repr(m.group(1)), m.group(2), m.group(3), m.group(4)[:90])
    for kw in ["playStyleEaIds:", "playStylePlusEaIds:"]:
        for m in list(re.finditer(re.escape(kw) + r'(\$R\[\d+\]|\[[^\]]*\])', h))[:3]:
            print("  ", kw, m.group(1), m.start())
    m = re.search(r'\$R\[25\]=(\[[^\]]*\])', h); print("  R25", m.group(1) if m else None)
    m = re.search(r'\$R\[26\]=(\[[^\]]*\])', h); print("  R26", m.group(1) if m else None)
