"""Probe 5: Vetlesen after the new EA data (positions from EA FC 27) and the new plan search."""
import json, sys
sys.path.insert(0, ".")
from fcrating.sources import local
for f in ("data/spesialkort.json", "data/ea_players.json"):
    for p in local.load_any(f):
        if "Vetlesen" in p.name:
            print(f, p.name, p.rarity, p.ovr, p.position, p.alt_positions, p.height_cm, p.source, len(p.attributes))
