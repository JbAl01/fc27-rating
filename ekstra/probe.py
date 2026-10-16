# Midlertidig probe (slettes). Leser cachet data; henter én EA-side og én offentlig FUT.GG-spillerside.
import json, re, sys, statistics, math
from pathlib import Path
sys.path.insert(0, ".")
from fcrating.sources import local, ea_ratings
from fcrating.model import load_config
from fcrating.runs import _sim_value, distance, similarity_stats, similarity_pct
cfg = load_config(); rc = cfg["weights"]["run_ai"]
def load(p):
    return local.load_json(p) if Path(p).exists() else []
ea = load("data/ea_players.json"); sp = load("data/spesialkort.json")
print("EA", len(ea), "spesial", len(sp))
allp = ea + sp
def d(p):
    return {"attributes": p.attributes, "height_cm": p.height_cm, "work_rate_att": p.work_rate_att, "name": p.name}
ler = [p for p in allp if "leroux" in p.name.lower()]
for p in ler:
    print("LEROUX", p.name, p.rarity, p.ovr, p.position, p.alt_positions, p.source, p.id, p.base_id, p.height_cm, p.work_rate_att, p.gender, p.estimated)
    print("  attrs", len(p.attributes), json.dumps(p.attributes)[:900])
keys = list(rc["similar"]["features"]); keys = [k for k in keys if not k.startswith("_")]
miss = {k: sum(1 for p in allp if _sim_value(d(p), k, rc) is None) for k in keys}
print("missing per feature", miss, "of", len(allp))
zero = {k: sum(1 for p in allp if (p.attributes or {}).get(k) == 0) for k in keys}
print("zero per feature", zero)
fake = [d(p) | {"run_ai": 1} for p in allp]
stats = similarity_stats(fake, rc)
print("stats", {k: (round(m,1), round(s,1)) for k, (m, s) in stats.items()})
import random; random.seed(1)
sample = random.sample(allp, 400)
if ler:
    L = d(ler[0])
    sims = []
    for p in sample:
        dd = distance(d(p), L, stats, rc)
        if dd is not None: sims.append(similarity_pct(dd))
    print("Leroux likhet til tilfeldige kort: median", statistics.median(sims), "max", max(sims))
    # how often is Leroux the closest card to a random card among the pool of all
    pool = random.sample(allp, 3000) + ler
    win = 0
    for p in sample[:60]:
        best = min(((distance(d(p), d(q), stats, rc) or 99, q.name) for q in pool if q is not p), key=lambda t: t[0])
        win += "leroux" in best[1].lower()
        if p is sample[0] or "leroux" in best[1].lower(): print("  nearest for", p.name, "->", best)
    print("Leroux nærmest for", win, "av 60")
# cards with few attributes
few = sorted(allp, key=lambda p: len(p.attributes))[:15]
print("færrest attributter:", [(p.name, p.rarity, len(p.attributes), p.source) for p in few])
print("birthdate i EA-filen:", sum(1 for p in ea if getattr(p, "birthdate", None)))
# EA raw item: birthdate format
try:
    cs = json.load(open("config/sources.json"))["ea_ratings"]
    data = ea_ratings.next_data(ea_ratings._get_html(cs["html_url_template"].format(page=1), cs.get("html_user_agent") or "Mozilla/5.0"))
    items = ea_ratings._dig(data, cs.get("html_items_path", "props.pageProps.ratingDetails.items"))
    it = items[0]
    print("EA item keys", sorted(it.keys()))
    print("EA birth fields", {k: v for k, v in it.items() if "birth" in k.lower() or "age" == k.lower()})
except Exception as e:
    print("EA ERR", e)
# FUT.GG public player page: roles markup
try:
    from fcrating.net import PoliteFetcher
    f = PoliteFetcher(user_agent="fc27-rating (personlig bruk)", delay_seconds=2)
    html = f.get("https://www.fut.gg/players/212198/27-212198/")
    print("FUTGG len", len(html))
    for w in ["Roles", "Role", "++", "Playmaker", "Advanced Forward"]:
        for m in list(re.finditer(re.escape(w), html))[:3]:
            print("  ", w, "@", m.start(), repr(html[max(0, m.start()-300):m.start()+300]))
    Path("/tmp/futgg_page.html").write_text(html)
except Exception as e:
    print("FUTGG ERR", e)
