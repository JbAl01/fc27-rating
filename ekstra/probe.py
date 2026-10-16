import re, json, gzip, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
            return r.status, b.decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", "ERR"), str(e)[:300]
for url in ["https://www.fut.gg/players/268703-nicolo-cambiaghi/27-268703/",
            "https://www.fut.gg/api/fut/player-item-definitions/27/268703/",
            "https://www.fut.gg/api/fut/players/v2/27/?search=cambiaghi",
            "https://www.fut.gg/players/?name=cambiaghi",
            "https://www.futbin.com/27/player/1/nicolo-cambiaghi"]:
    st, body = get(url)
    print("=====", url, st, len(body))
    low = body
    for kw in ["playstyle", "playStyle", "Gamechanger", "Whipped", "Technical", "__NEXT_DATA__", "self.__next_f", "api/fut"]:
        i = low.find(kw)
        print("  ", kw, i, repr(low[max(0, i-150):i+250]) if i >= 0 else "")
    if st == 200 and "api" in url: print(body[:3000])
