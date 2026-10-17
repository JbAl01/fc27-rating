import os
from fcrating import net
os.makedirs("/tmp/pages", exist_ok=True)
log = open("/tmp/an.txt", "w")
f = net.PoliteFetcher(user_agent="fc27-rating/0.2 (personlig bruk)", delay_seconds=2)
pages = {"gold": "231747/27-231747", "silver": "264938/27-264938", "bronze": "269875/27-269875", "icon": "237067/27-67345931",
         "totw": "227203/27-67336067", "fs": "271446/27-50603094", "dfg": "252145/27-67361009", "ce": "227203/27-100890499",
         "otw": "216393/27-50548041", "sf": "193165/27-50524813", "potm": "247827/27-84133907", "pre_icon": "0/27-84129155"}
for k, u in pages.items():
    try:
        h = f.get(f"https://www.fut.gg/players/{u}/")
        open(f"/tmp/pages/{k}.html", "w").write(h)
        log.write(f"{k} {len(h)}\n")
    except Exception as e:
        log.write(f"{k} fail {e!r}\n")
log.close()
