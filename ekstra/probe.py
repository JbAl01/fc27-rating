# Midlertidig probe (slettes): rolle-id-er på offentlige FUT.GG-spillersider -> posisjoner.
import json, re, sys
sys.path.insert(0, ".")
from fcrating.net import PoliteFetcher
f = PoliteFetcher(user_agent="fc27-rating (personlig bruk)", delay_seconds=3)
ids = [239085, 203376, 212831, 209331, 231866, 231747, 232656, 235212, 256790, 238794, 212622, 239053,
       246669, 251854, 253149, 252371, 222665, 241721, 230621, 233731, 245367, 238074, 236772, 247635,
       264240, 237692, 220834, 240130, 228702, 239818]
SC = re.compile(r'role:(\d+),chemistryStyle:1,score:[\d.]+,rank:\d+,isPlus:!(\d),isPlusPlus:!(\d)')
out = []
for pid in ids:
    try:
        h = f.get(f"https://www.fut.gg/players/{pid}/27-{pid}/")
    except Exception as e:
        print(pid, "ERR", e); continue
    m = re.search(r'eaId:%d,' % pid, h)
    seg = h
    pos = re.search(r'position:(\d+),alternativePositionIds:\$R\[\d+\]=\[([\d,]*)\]', h)
    rp = re.search(r'rolesPlus:\$R\[\d+\]=\[([\d,]*)\],rolesPlusPlus:\$R\[\d+\]=\[([\d,]*)\]', h)
    name = re.search(r'headerTitle:"([^"]+)"', h)
    roles = {}
    for r, p, pp in SC.findall(h):
        roles.setdefault(r, 2 if pp == "0" else 1 if p == "0" else 0)
    rec = {"id": pid, "name": name.group(1) if name else None, "pos": pos.groups() if pos else None,
           "rp": rp.groups() if rp else None, "scores": roles}
    print(json.dumps(rec, ensure_ascii=False))
    out.append(rec)
# the JS bundle: role names?
try:
    js = f.get("https://assets.fut.gg/ts/assets/index-Cxb7_ZYT.js")
    print("JS len", len(js))
    for w in ["Shadow Striker", "Poacher", "Box-to-Box", "Deep-Lying", "Advanced Forward"]:
        for m in list(re.finditer(re.escape(w), js))[:2]:
            print("JS", w, repr(js[max(0, m.start()-400):m.start()+400]))
    open("/tmp/futgg_page.html", "w").write(js)
except Exception as e:
    print("JS ERR", e)
