import json
log = open("/tmp/an.txt", "w")
k = json.load(open("data/cache/futgg/kort.json"))
ic = json.load(open("data/cache/futgg/ikoner.json"))
ok = [v for v in k.values() if not v.get("missing")]
log.write(f"cards {len(k)} ok {len(ok)} with cc {sum(1 for v in ok if v.get('cc'))} old col only {sum(1 for v in ok if v.get('col') and not v.get('cc'))}\n")
log.write(f"icons {len(ic)} with glyph {sum(1 for v in ic.values() if v.get('g'))}\n")
log.write("no glyph: " + ", ".join(sorted(n for n, v in ic.items() if not v.get('g'))) + "\n")
log.close()
