"""Probe 4: raw fields of one EA FC 27 item (height, weight, stats and abilities format)."""
import json, sys
sys.path.insert(0, ".")
from fcrating.sources import ea_ratings
html = ea_ratings._get_html("https://www.ea.com/games/ea-sports-fc/ratings?search=Vetlesen", "Mozilla/5.0 (compatible; fc27-rating/0.3)")
it = ea_ratings.next_data(html)["props"]["pageProps"]["ratingDetails"]["items"][0]
for k in sorted(it):
    v = it[k]
    print(k, "=", json.dumps(v, ensure_ascii=False)[:500])
