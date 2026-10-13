"""Check the model against what you feel in the game: blind A-vs-B tests.

No formula built from card data can be 99 % right: EA does not publish its animation
curves, and lag, your opponent and your own habits move the feel more than a couple of
attribute points. What can be measured is how often the model agrees with you. So:

1. Play two cards in the same drill or match (ideally without knowing which is which,
   or with someone else picking), and note which one played better, and how clearly.
2. Save it:  py -m fcrating test-par FILER --a "Pichon" --b "Vicky López" --vinner a --styrke 2
3. Evaluate: py -m fcrating evaluer FILER

The evaluation shows how often IGR picks the same winner as you (split by how far apart
the cards are), which part of the model (feel, Løps-AI, pace, off-balance ...) agrees most
with you, and a Bradley-Terry ranking of the cards from your own tests. That tells you
which weights to turn up or down, and how much the numbers can be trusted.
"""
from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
TEST_FILE = ROOT / "data" / "tester.csv"
FIELDS = ["dato", "a", "a_versjon", "b", "b_versjon", "vinner", "styrke", "type", "posisjon", "notat"]
TYPES = {"alt": "alt", "ball": "med ball", "lop": "uten ball", "løp": "uten ball"}
COMPONENTS = [("igr", "IGR"), ("feel", "Følelse"), ("run", "Løps-AI"), ("pace", "Fart"), ("skill", "Ferdigheter"),
              ("obd", "Off-balance"), ("ovr", "OVR")]


def _norm(s: str) -> str:
    from .promo import norm_name
    return norm_name(s or "")


def find_card(results: List[dict], spec: str, version: Optional[str] = None) -> Tuple[Optional[dict], List[dict]]:
    """'Name' or 'Name|Version'. Exact name first, then names that contain it; with several
    versions the one matching the version text, else the highest OVR. Returns (card, all hits)."""
    if "|" in spec and not version:
        spec, version = spec.split("|", 1)
    want = _norm(spec)
    hits = [r for r in results if _norm(r["name"]) == want] or [r for r in results if want and want in _norm(r["name"])]
    if version:
        v = version.lower()
        hits = [r for r in hits if v in (r.get("rarity") or "").lower()] or hits
    if not hits:
        return None, []
    return max(hits, key=lambda r: (r.get("ovr") or 0, r["by_group"].get(r.get("position_group") or "", {}).get("igr", 0))), hits


def common_group(a: dict, b: dict, wanted: Optional[str] = None) -> Optional[str]:
    if wanted and wanted in a["by_group"] and wanted in b["by_group"]:
        return wanted
    for g in (a.get("position_group"), b.get("position_group")):
        if g and g in a["by_group"] and g in b["by_group"]:
            return g
    both = [g for g in a["by_group"] if g in b["by_group"]]
    return both[0] if both else None


def component(r: dict, g: str, key: str) -> Optional[float]:
    gr = r["by_group"].get(g, {})
    if key == "igr":
        return gr.get("igr")
    if key == "feel":
        return r.get("feel")
    if key == "run":
        return (r.get("run_ai") or {}).get("score")
    if key == "pace":
        return gr.get("pace")
    if key == "skill":
        return gr.get("skill")
    if key == "obd":
        return r.get("off_balance_dribbling")
    if key == "ovr":
        return r.get("ovr")
    return None


def add_test(row: dict, path: Path = TEST_FILE) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
    return len(load_tests(path))


def load_tests(path: Path = TEST_FILE) -> List[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f, delimiter=";") if r.get("a") and r.get("b")]


def bradley_terry(pairs: List[Tuple[str, str, float]], iters: int = 200) -> Dict[str, float]:
    """Strength per card from (winner, loser, weight) pairs (MM algorithm, a little prior so
    a card with only wins does not run off to infinity). Returned on a log scale (0 = average)."""
    players = sorted({p for a, b, _ in pairs for p in (a, b)})
    if not players:
        return {}
    wins = {p: 0.5 for p in players}  # prior: half a win and half a loss against an average card
    games: Dict[Tuple[str, str], float] = {}
    for a, b, w in pairs:
        wins[a] += w
        games[(a, b)] = games.get((a, b), 0.0) + w
        games[(b, a)] = games.get((b, a), 0.0) + w
    s = {p: 1.0 for p in players}
    for _ in range(iters):
        new = {}
        for p in players:
            den = 1.0 / (s[p] + 1.0)  # the prior games against a strength-1 card
            for (x, y), n in games.items():
                if x == p:
                    den += (n / 2) / (s[p] + s[y])
            new[p] = wins[p] / den if den else s[p]
        g = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        s = {p: v / g for p, v in new.items()}
    return {p: round(math.log(v), 2) for p, v in s.items()}


def evaluate(tests: List[dict], results: List[dict]) -> dict:
    """How often each part of the model picks the same winner as you."""
    from .runs import spearman
    rows, missing = [], []
    for t in tests:
        a, _ = find_card(results, t["a"], t.get("a_versjon") or None)
        b, _ = find_card(results, t["b"], t.get("b_versjon") or None)
        if not a or not b:
            missing.append(t["a"] if not a else t["b"])
            continue
        g = common_group(a, b, (t.get("posisjon") or "").upper() or None)
        if not g:
            missing.append(f"{t['a']} / {t['b']} (ingen felles posisjon)")
            continue
        win = (t.get("vinner") or "").strip().lower()
        if win not in ("a", "b", "lik"):
            continue
        strength = min(3, max(1, int(t.get("styrke") or 1)))
        rows.append({"a": a, "b": b, "g": g, "win": win, "w": strength, "type": TYPES.get((t.get("type") or "alt").lower(), "alt")})
    decided = [r for r in rows if r["win"] != "lik"]
    out = {"tests": len(rows), "decided": len(decided), "ties": len(rows) - len(decided), "missing": missing, "comp": [], "gaps": [],
           "bt": [], "rho": None, "wrong": [], "by_type": {}}
    def agreement(subset):
        res = []
        for key, label in COMPONENTS:
            agree = total = 0.0
            for r in subset:
                va, vb = component(r["a"], r["g"], key), component(r["b"], r["g"], key)
                if va is None or vb is None or va == vb:
                    continue
                total += r["w"]
                if (va > vb) == (r["win"] == "a"):
                    agree += r["w"]
            if total:
                res.append([label, round(100 * agree / total), int(total)])
        return res

    out["comp"] = agreement(decided)
    # Split by what was tested: a "med ball" test should agree with Følelse/Off-balance, a
    # "uten ball" test with Løps-AI. If not, that part of the model is the one to adjust.
    out["by_type"] = {t: agreement([r for r in decided if r["type"] == t])
                      for t in ("med ball", "uten ball") if any(r["type"] == t for r in decided)}
    buckets = [("under 1", 0, 1), ("1-3", 1, 3), ("over 3", 3, 999)]
    for name, lo, hi in buckets:
        agree = n = 0
        for r in decided:
            va, vb = component(r["a"], r["g"], "igr"), component(r["b"], r["g"], "igr")
            gap = abs(va - vb)
            if lo <= gap < hi and va != vb:
                n += 1
                agree += (va > vb) == (r["win"] == "a")
        if n:
            out["gaps"].append([name, round(100 * agree / n), n])
    key = lambda r: f"{r['name']} ({r.get('rarity') or ''})"
    pairs, by = [], {}
    for r in decided:
        wa, la = (r["a"], r["b"]) if r["win"] == "a" else (r["b"], r["a"])
        pairs.append((key(wa), key(la), float(r["w"])))
        by[key(r["a"])], by[key(r["b"])] = (r["a"], r["g"]), (r["b"], r["g"])
    bt = bradley_terry(pairs)
    counts: Dict[str, int] = {}
    for a, b, _ in pairs:
        counts[a] = counts.get(a, 0) + 1
        counts[b] = counts.get(b, 0) + 1
    ranked = sorted(bt.items(), key=lambda t: t[1], reverse=True)
    out["bt"] = [[k, v, counts.get(k, 0), component(by[k][0], by[k][1], "igr")] for k, v in ranked]
    enough = [(v, component(by[k][0], by[k][1], "igr")) for k, v in bt.items() if counts.get(k, 0) >= 2]
    if len(enough) >= 4:
        out["rho"] = spearman([x for x, _ in enough], [y for _, y in enough])
    for r in decided:
        va, vb = component(r["a"], r["g"], "igr"), component(r["b"], r["g"], "igr")
        if va is not None and vb is not None and (va > vb) != (r["win"] == "a") and abs(va - vb) >= 2:
            w, l = (r["a"], r["b"]) if r["win"] == "a" else (r["b"], r["a"])
            out["wrong"].append([w["name"], l["name"], round(abs(va - vb), 1), r["type"]])
    return out


def report_lines(ev: dict) -> List[str]:
    lines = [f"Tester: {ev['tests']} ({ev['decided']} med vinner, {ev['ties']} like)."]
    if ev["missing"]:
        lines.append("Fant ikke: " + ", ".join(sorted(set(ev["missing"]))[:6]))
    if not ev["decided"]:
        lines.append("Ingen tester med vinner ennå. Legg til med: py -m fcrating test-par FILER --a NAVN --b NAVN --vinner a")
        return lines
    lines.append("\nHvor ofte hver del av modellen velger samme vinner som deg (vektet med styrke):")
    for label, pct, n in sorted(ev["comp"], key=lambda t: t[1], reverse=True):
        lines.append(f"  {label:<12} {pct:>3} %  ({n} vektede tester)")
    for typ, comp_t in ev.get("by_type", {}).items():
        if comp_t:
            top = sorted(comp_t, key=lambda t: t[1], reverse=True)[:4]
            lines.append(f"  Bare «{typ}»-tester: " + ", ".join(f"{l} {p} %" for l, p, _ in top) + f"  ({top[0][2]} vektede)")
    if ev["gaps"]:
        lines.append("\nIGR treffer etter hvor langt fra hverandre kortene er:")
        for name, pct, n in ev["gaps"]:
            lines.append(f"  IGR-forskjell {name:<8} {pct:>3} %  ({n} tester)")
    comp = {label: pct for label, pct, _ in ev["comp"]}
    best = max(ev["comp"], key=lambda t: t[1]) if ev["comp"] else None
    if best and best[0] != "IGR" and comp.get("IGR") is not None and best[1] >= comp["IGR"] + 10 and best[2] >= 8:
        lines.append(f"\nHint: {best[0]} treffer deg bedre enn IGR ({best[1]} mot {comp['IGR']} %). Vurder å gi {best[0].lower()} mer vekt.")
    if ev["rho"] is not None:
        lines.append(f"\nRangering fra testene dine mot IGR (Spearman, kort med 2+ tester): {ev['rho']}")
        lines.append("  Over 0.75 er godt. Med 25 kort må den være over ca. 0.40 for å være mer enn tilfeldig.")
    if ev["bt"]:
        lines.append("\nKortene etter dine tester (Bradley-Terry, 0 = snitt):")
        for k, v, n, igr in ev["bt"][:15]:
            lines.append(f"  {v:+5.2f}  {k}  ({n} tester, IGR {igr})")
    if ev["wrong"]:
        lines.append("\nDer IGR bommet med 2+ poeng (verdt å se på):")
        for w, l, gap, typ in ev["wrong"][:8]:
            lines.append(f"  {w} slo {l} ({typ}), men IGR hadde {l} {gap} foran")
    return lines


def today() -> str:
    return date.today().isoformat()
