"""What people actually play: FUT.GG's 'Most Used Players' page (fut.gg/tactics/most-used-players/).

The page lists, for every position, the cards used most by the pros (FUT Champions top players,
a couple of hundred squads) and by the FUT.GG community (several hundred thousand squads), with
the share of squads that play the card there. That is the closest thing to the market's verdict
(the cards that sell out) that can be read without FUT.GG's closed API: a card many people choose
over cheaper and more expensive cards is good in game.

It is shown on the cards ("meta i spillet") and used to check the model: the cards people play
should rank high in our IGR as well. It is not added to IGR, because use also follows price and
how many copies exist, not only how good a card is.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

URL = "https://www.fut.gg/tactics/most-used-players/"
_SECTION = re.compile(r'(pros|community):\$R\[\d+\]=\{count:(\d+),positions')
_POS = re.compile(r'position:"([A-Z]{2,3})",sampleSize:(\d+)')
_PLAYER = re.compile(r'playerType:"players",game:"27",id:\d+,eaId:(\d+)')
_SHARE = re.compile(r'\},count:(\d+),pct:([\d.]+)\}')
GROUP = {"ST": "ST", "CF": "ST", "LW": "W", "RW": "W", "LM": "W", "RM": "W", "CAM": "CAM", "CM": "CM",
         "CDM": "CDM", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "CB": "CB", "GK": "GK"}


def parse(html: str) -> Optional[dict]:
    """{"pros": {"squads": N, "cards": {card id: {position: pct}}}, "community": {...}}, or None."""
    sections = [(m.start(), m.group(1), int(m.group(2))) for m in _SECTION.finditer(html)]
    if not sections:
        return None
    positions = [(m.start(), m.group(1), int(m.group(2))) for m in _POS.finditer(html)]
    out = {name: {"squads": n, "cards": {}, "samples": {}} for _, name, n in sections}

    def last_before(items, at):
        best = None
        for it in items:
            if it[0] < at:
                best = it
            else:
                break
        return best

    for m in _PLAYER.finditer(html):
        sec, pos = last_before(sections, m.start()), last_before(positions, m.start())
        sh = _SHARE.search(html, m.end())
        if not sec or not pos or not sh:
            continue
        nxt = _PLAYER.search(html, m.end())
        if nxt and nxt.start() < sh.start():   # the share belongs to a later card: the layout changed
            continue
        part = out[sec[1]]
        part["samples"][pos[1]] = pos[2]
        card = part["cards"].setdefault(m.group(1), {})
        card[pos[1]] = max(card.get(pos[1], 0.0), float(sh.group(2)))
    if not any(p["cards"] for p in out.values()):
        return None
    return out


def fetch(fetcher, folder: str, log=print) -> Optional[dict]:
    """Read the page once and save it in <folder>/bruk.json (kept if the page cannot be read)."""
    try:
        data = parse(fetcher.get(URL))
    except Exception as exc:   # FUT.GG down or changed: keep the last saved
        log(f"FUT.GG mest brukte: kunne ikke lese ({exc})")
        return None
    if not data:
        log("FUT.GG mest brukte: fant ingen kort på siden (oppsettet kan være endret)")
        return None
    data["t"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = Path(folder)
    p.mkdir(parents=True, exist_ok=True)
    tmp = p / "bruk.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p / "bruk.json")
    n = {k: len(v["cards"]) for k, v in data.items() if isinstance(v, dict)}
    log(f"FUT.GG mest brukte: {n.get('pros', 0)} kort hos proffene, {n.get('community', 0)} hos FUT.GG-brukerne")
    return data


def load(folder: str) -> Optional[dict]:
    p = Path(folder) / "bruk.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def usage_of(data: Optional[dict], card_id) -> Optional[dict]:
    """{"pro": [pct, position], "com": [pct, position], "t": date} for one card (best position), or None."""
    if not data or card_id is None:
        return None
    out = {}
    for key, name in (("pro", "pros"), ("com", "community")):
        c = (data.get(name) or {}).get("cards", {}).get(str(card_id))
        if c:
            pos, pct = max(c.items(), key=lambda kv: kv[1])
            out[key] = [pct, pos]
    if not out:
        return None
    out["t"] = data.get("t")
    return out


def check_model(results: List[dict], log=print) -> Optional[dict]:
    """How the model ranks the cards people actually play: the median top % in their position among
    the cards the pros use, and how many of them are outside the top 10 %. Printed by every run, so a
    model change that pushes meta cards down shows up at once."""
    out = {}
    for key, label in (("pro", "proffene"), ("com", "FUT.GG-brukerne")):
        tops, low = [], []
        for r in results:
            u = (r.get("usage") or {}).get(key)
            if not u:
                continue
            g = GROUP.get(u[1])
            e = r["by_group"].get(g or "")
            if not e or e.get("top_pct") is None:
                continue
            tops.append(e["top_pct"])
            if e["top_pct"] > 10:
                low.append((e["top_pct"], r["name"], u[1], u[0]))
        if not tops:
            continue
        tops.sort()
        med = tops[len(tops) // 2]
        low.sort(reverse=True)
        out[key] = {"n": len(tops), "median_top": med, "outside_top10": len(low)}
        log(f"Modellsjekk ({label}): {len(tops)} kort, median topp {med} % i posisjonen, "
            f"{len(low)} utenfor topp 10 %" + (": " + ", ".join(f"{n} ({p} {pct} %, hos oss topp {t} %)" for t, n, p, pct in low[:6]) if low else ""))
    return out or None
