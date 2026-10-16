"""Command line: python -m fcrating <command> ...

  rate         Rate players from JSON/CSV files and write output/ (CSV, JSON, HTML)
  explain      Show the full breakdown for one player
  evo          Rank players by evo potential
  perler       Hidden gems: forwards whose Løps-AI is far above what OVR suggests
  lignende     Cards with a run profile like a card you like (e.g. Geyse FC 25)
  kalibrer     Fit the Løps-AI weights to runs you have counted yourself
  kombo        Rank cards by a combination of profile categories (e.g. følelse + løp + dribling)
  evolab       How good each card can become through evolutions (live evo plan + simulated futures)
  evo-import   Add an evolution from text copied from FUTBIN / FUT.GG
  test-par     Save a blind A-vs-B test (which card played better)
  evaluer      How well the model agrees with your blind tests
  brukt        Evos you have used up on other cards (Evo Lab plans without them)
  import-text  Turn text copied from a player page into a player record
  fetch-ea     Download the EA ratings database (needs url_template in config/sources.json)
  watch        Fetch + rate on a schedule, keep output/ up to date
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .explain import why_lines
from .model import evo_potential, group_label, load_config, rank_evos, rate
from .report import write_outputs
from .schema import Player
from .sources import local as local_src

ROOT = Path(__file__).resolve().parent.parent


def _load_players(files: List[str]) -> List[Player]:
    players: List[Player] = []
    seen = set()
    for f in files:
        for p in local_src.load_any(f):
            if p.uid in seen:  # same card loaded twice (e.g. the same file given twice)
                continue
            seen.add(p.uid)
            players.append(p)
    from .specials import apply_work_rates, load_work_rates, prefer_fc27_base
    players, msg = prefer_fc27_base(players)
    if msg:
        print(msg)
    # EA's base cards have no work rate; FIFA Rosters' saved list has it for every card
    table = load_work_rates(str(ROOT / "data" / "cache"))
    if table:
        apply_work_rates(players, table)
    _fill_club_info(players)
    from .sources import futgg
    n = futgg.apply(players, futgg.load_cards(str(ROOT / "data" / "cache" / "futgg")))
    if n:
        print(f"PlayStyles fra FUT.GG brukt på {n} kort.")
    return players


def _fill_club_info(players: List[Player]) -> None:
    """Cards without club/league/nation (special cards built before the fields existed, FC 27 base
    cards from FIFA Rosters) get them from the EA card with the same player id. Icons get league "Icons"."""
    table = {}
    for p in players:
        if p.league or p.nation or p.birthdate:
            table.setdefault(str(p.id), p)
    for p in players:
        if not p.league and "icon" in (p.rarity or "").lower():
            p.league = "Icons"
        if p.league and p.nation and p.birthdate:
            continue
        src = table.get(str(p.base_id)) or table.get(str(p.id))
        if src is None or src is p:
            continue
        p.club = p.club or src.club
        p.league = p.league or src.league
        p.nation = p.nation or src.nation
        p.birthdate = p.birthdate or src.birthdate


def _ranked(files: List[str], chem: Optional[str] = None):
    from .model import rank_by_position
    cfg = load_config()
    players = _load_players(files)
    results = [rate(p, cfg, chem=chem) for p in players]
    rank_by_position(results, cfg)
    return cfg, players, results


def _chem_arg(value: Optional[str]) -> Optional[str]:
    if not value or value.lower() in ("none", "ingen", "0"):
        return None
    if value.lower() == "best":
        return "best"
    return value[:1].upper() + value[1:]


def _fmt(v, width, digits=1):
    if v is None:
        s = "-"
    elif isinstance(v, float):
        s = f"{v:.{digits}f}"
    else:
        s = str(v)
    return s[:width].rjust(width) if not isinstance(v, str) else s[:width].ljust(width)


GROUP_ORDER = ["ST", "W", "CAM", "CM", "CDM", "FB", "CB", "GK"]


def _display_name(r: dict, alt: bool) -> str:
    name = r["name"]
    version = (r.get("rarity") or "").replace("FC 27 ", "")
    if version and r.get("status"):  # special cards carry a status
        name = f"{name} [{version}{', lekket' if r['status'] == 'lekket' else ''}]"
    return name + (" (alt)" if alt else "")


def _row(i: int, r: dict, gr: dict, alt: bool) -> str:
    name = _display_name(r, alt)
    return (f"{i:>4}  {_fmt(name, 40)} {_fmt(r['ovr'], 3)}  {gr['igr']:>5.1f} {gr['pos_tier']:<1}  "
            f"{('#' + str(gr['rank']) + '/' + str(gr['of'])):>9} {gr['top_pct']:>5.0f} %  {_fmt(r['feel'], 7)} {_fmt(gr['pace'], 5)} "
            f"{_fmt(gr['skill'], 8)} {gr['playstyles']:>4.1f} {gr['role']:>5.1f}  {_fmt(r['accelerate'] or '?', 10)} "
            f"{_fmt((r.get('run_ai') or {}).get('score') if 'run' in gr else None, 7)}"
            f"{'  perle' if gr.get('run', {}).get('gem') else ''}")


def print_position_table(results: List[dict], group: str, top: int) -> None:
    from .model import primary_group
    pool = [r for r in results if group in r["by_group"]]
    if not pool:
        return
    pool.sort(key=lambda r: r["by_group"][group]["igr"], reverse=True)
    n = len(pool)
    basis = pool[0]["by_group"][group]["tier_basis"]
    print(f"\n{group_label(group).upper()} ({n} spillere, tier etter {basis})")
    head = (f"{'#':>4}  {'Spiller':<40} {'OVR':>3}  {'IGR':>5} {'T':<1}  {'Plass':>9} {'Topp':>7}  "
            f"{'Følelse':>7} {'Fart':>5} {'Ferdigh.':>8} {'PS':>4} {'Rolle':>5}  {'AcceleRATE':<10} {'Løps-AI':>7}")
    print(head)
    print("-" * len(head))
    for i, r in enumerate(pool[:top], 1):
        print(_row(i, r, r["by_group"][group], alt=primary_group(r) != group))


def print_tables(results: List[dict], group: Optional[str], top: int) -> None:
    groups = [group] if group else [g for g in GROUP_ORDER if any(g in r["by_group"] for r in results)]
    for g in groups:
        print_position_table(results, g, top)


def _run_evolab(players, results, evos, cfg, out_dir, ignore_used=False):
    """Simulate evo paths for every card and write output/evolab.html. Returns the paths or None."""
    from . import evolab, evolab_report
    try:
        lab = evolab.load_lab_config()
    except FileNotFoundError:
        return None
    run = evolab.run(players, results, cfg, lab=lab, ignore_used=ignore_used)
    summary = evolab.summarize(run, players, results, cfg)
    evolab.update_evos(evos, summary, lab)
    return evolab_report.write(summary, results, run, cfg, out_dir, players)


def cmd_rate(args) -> int:
    from .model import rank_by_position
    cfg = load_config()
    players = _load_players(args.files)
    chem = _chem_arg(args.chem)
    results = [rate(p, cfg, chem=chem) for p in players]
    rank_by_position(results, cfg)
    from . import meta as meta_mod
    meta_info = meta_mod.apply(results, cfg, save=getattr(args, "lagre_meta_start", False))
    if meta_info.get("saved"):
        print(f"Lagret startnivået for Meta i {meta_mod.start_path()}")
    evos = {p.uid: evo_potential(p, cfg, chem=None if chem == "best" else chem) for p in players}
    rank_evos(evos, results)
    group = args.group.upper() if args.group else None
    lab_paths = None if getattr(args, "uten_evolab", False) else _run_evolab(
        players, results, evos, cfg, args.out, ignore_used=getattr(args, "ignorer_brukte", False))
    paths = write_outputs(results, evos, args.out, evolab=bool(lab_paths), meta_info=meta_info)  # write first, so output is saved even if printing fails
    print_tables(results, group, args.top if group else min(args.top, 10))
    print(f"\nSkrev {len(results)} spillere til {paths['html']}, {paths['csv']} og {paths['json']}")
    if lab_paths:
        print(f"Evo Lab: {lab_paths['html']} (og {lab_paths['csv']})")
    warned = [r for r in results if r["warnings"]]
    for r in warned[:15]:
        print(f"  Merk {r['name']}: {'; '.join(r['warnings'])}")
    if len(warned) > 15:
        print(f"  ... og {len(warned) - 15} spillere til med merknader (se ratings.csv)")
    return 0


def _name_matches(items, name: str, key=lambda x: x.name):
    """Exact name (ignoring case and accents) first; otherwise names containing it."""
    from .promo import norm_name
    want = norm_name(name)
    exact = [x for x in items if norm_name(key(x)) == want]
    return exact or [x for x in items if want in norm_name(key(x))]


def cmd_explain(args) -> int:
    from .model import rank_by_position
    cfg = load_config()
    all_players = _load_players(args.files)
    players = _name_matches(all_players, args.name)
    if not players:
        print(f"Fant ingen spiller som matcher '{args.name}'.")
        return 1
    chem = _chem_arg(args.chem)
    groups = [g.upper() for g in args.groups] if args.groups else None
    # rank against everyone in the same files, using their own positions
    others = [rate(p, cfg, chem=chem) for p in all_players if p not in players]
    for p in players:
        r = rate(p, cfg, chem=chem, groups=groups)
        rank_by_position(others + [r], cfg)
        evo = {p.uid: evo_potential(p, cfg, chem=None if chem == "best" else chem)}
        rank_evos(evo, others + [r])
        evo = evo[p.uid]
        print(f"\n{_display_name(r, False)}  (OVR {r['ovr']}, {'/'.join(r['positions'])}"
              f"{', kjemistil ' + r['chem_style'] if r['chem_style'] else ''})")
        prof = r.get("profile") or {}
        if prof.get("style"):
            print(f"  Stil: {prof['style']}" + (f". Passer hvis du liker: {', '.join(prof['likes'])}" if prof.get("likes") else ""))
        if prof.get("pct"):
            from .profile import style_keys
            labels = cfg["weights"]["profile"]["categories"]
            print("  Profil: " + ", ".join(f"{labels[k]['label']} {prof['cats'][k]:.0f} (topp {prof['pct'][k]:.0f} %)"
                                            for k in style_keys(cfg) if k in prof["pct"]))
        g0 = r.get("position_group") or r["best_group"]
        if g0 in r["by_group"]:
            print(f"\n  Hvorfor er {r['name']} rangert slik som {group_label(g0).lower()}?")
            for line in why_lines(r, g0, cfg["weights"]["blend"].get(g0)):
                print(f"    - {line}")
        if evo["eligible"]:
            print(f"\n  Evo: +{evo['boost']:.0f} på attributtene (OVR {r['ovr']} -> {evo['ovr_after']}), "
                  f"IGR {evo['igr_now']} -> {evo['igr_after']} ({evo['gain']:+.1f}), "
                  f"plass {evo['rank_now']} -> {evo['rank_after']} av {evo['of']}")
        else:
            print(f"\n  Evo: ikke med ({evo['reason']})")
        from .runs import run_group, run_lines
        from .schema import GROUP_PLURAL_NO
        rg = run_group(r, cfg["weights"]["run_ai"]["groups"]) if r.get("run_ai") else None
        if rg:
            print(f"\n  Løps-AI som {group_label(rg).lower()}:")
            for line in run_lines(r, rg, GROUP_PLURAL_NO[rg]):
                print(f"    - {line}")
        print("\n  Utregning:")
        print(f"  AcceleRATE: {r['accelerate'] or 'ukjent'} - {r['accelerate_reason']}")
        print(f"  Off-Balance Dribbling: {r['off_balance_dribbling']} (snittet av Agility, Balance og Dribbling, som EasySBC; "
              f"kommer inn fra {cfg['weights'].get('off_balance', {}).get('start', 75)})")
        hs = r.get("hard_to_stop")
        if hs:
            print(f"  Vanskelig å stoppe: {hs['score']} (med ball {hs['ball']}, uten ball på løp {hs['run']}). "
                  "Strength, Balance, Sprint Speed og Acceleration, med ball også Ball Control og Dribbling; "
                  "Lengthy, Rapid, Press Proven, Enforcer og Bruiser gir litt ekstra")
        fp = r["feel_parts"]
        print(f"  Følelse {r['feel']}: attributter {fp.get('attributes')}, høyde {fp.get('height', 0):+}, "
              f"AcceleRATE {fp.get('accelerate', 0):+}, kroppstype {fp.get('body_type', 0):+}")
        for g, gr in sorted(r["by_group"].items(), key=lambda kv: kv[1]["igr"], reverse=True):
            print(f"\n  {group_label(g)}: IGR {gr['igr']}  tier {gr['pos_tier']}  "
                  f"plass {gr['rank']} av {gr['of']} (topp {gr['top_pct']} %)")
            extra = (f", løps-AI {gr['run_score']}" if gr.get("run_score") is not None else "") + \
                (f", stopp {gr['stop_score']}" if gr.get("stop_score") is not None else "")
            print(f"    kjerne {gr['core']} = følelse {gr['feel']}, fart {gr['pace']}, ferdighet {gr['skill']}{extra}")
            print(f"    PlayStyles {gr['playstyles']:+.2f}, rolle {gr['role']:+.1f} ({gr['role_name'] or 'ingen data'}), "
                  f"svakfot {gr['weak_foot']:+.2f}, skill moves {gr['skill_moves']:+.2f}")
            for d in gr["playstyle_details"]:
                print(f"      {d['name']:<20} {d['points']:+.2f}  (verdi {d['value']}, relevans {d['relevance']}, "
                      f"synergi {d['synergy']})")
        if r["warnings"]:
            print(f"  Merk: {'; '.join(r['warnings'])}")
    return 0


def cmd_evo(args) -> int:
    """Eligible cards only, ranked by where they end up after evolutions."""
    from .model import rank_by_position
    cfg = load_config()
    players = _load_players(args.files)
    results = [rate(p, cfg) for p in players]
    rank_by_position(results, cfg)
    by_uid = {r["uid"]: r for r in results}
    evos = {p.uid: evo_potential(p, cfg) for p in players}
    rank_evos(evos, results)
    group = args.group.upper() if args.group else None
    ok = [e for e in evos.values() if e["eligible"] and (not group or e["group"] == group)]
    sort_key = "gain" if args.sort == "gevinst" else "igr_after"
    ok.sort(key=lambda e: (e[sort_key], e["igr_after"]), reverse=True)
    skipped = len(evos) - sum(1 for e in evos.values() if e["eligible"])
    ecfg = cfg["weights"]["evo"]
    print(f"Evo-kandidater: {len(ok)} kort kan evolueres ({skipped} er ikke med: over OVR {ecfg['max_ovr']}, "
          f"Icons/Heroes, lekkasjer og keepere).")
    print(f"Hver attributt øker med ({ecfg['target_ovr']} - OVR) x {ecfg['points_per_ovr']}, maks "
          f"{ecfg['max_boost']}. Lavere OVR gir altså større økning.\n")
    head = (f"{'#':>4}  {'Spiller':<36} {'OVR':>7}  {'Posisjon':<11} {'IGR nå':>6} {'Etter':>6} {'Gevinst':>7}  "
            f"{'Plass nå -> etter':<22} {'AcceleRATE nå -> etter'}")
    print(head)
    print("-" * len(head))
    for i, e in enumerate(ok[:args.top], 1):
        r = by_uid.get(e["uid"]) or {"name": e["name"]}
        ovr = f"{e['ovr']}->{e['ovr_after']}"
        place = f"#{e['rank_now']} -> #{e['rank_after']} av {e['of']}"
        print(f"{i:>4}  {_fmt(_display_name(r, False), 36)} {ovr:>7}  {_fmt(group_label(e['group']), 11)} "
              f"{e['igr_now']:>6.1f} {e['igr_after']:>6.1f} {e['gain']:>+7.1f}  {place:<22} "
              f"{e['accelerate_now'] or '?'} -> {e['accelerate_after'] or '?'}")
    return 0


def cmd_perler(args) -> int:
    """Forwards with Løps-AI far above what their OVR suggests."""
    from .runs import FEATURE_LABELS, run_group
    from .schema import GROUP_PLURAL_NO
    cfg, _, results = _ranked(args.files)
    rc = cfg["weights"]["run_ai"]
    groups = [args.group.upper()] if args.group else rc["groups"]
    gem = rc["gem"]
    for why in rc.get("dropped", {}).values():
        print(f"Arbeidsraten er ikke med i Løps-AI: {why}, så den skiller ikke kortene.")
    for g in groups:
        pool = [r for r in results if r.get("run_ai") and "run" in r["by_group"].get(g, {})]
        if not pool:
            continue
        rows = pool if args.alle else [r for r in pool if r["by_group"][g]["run"]["gem"]]
        if args.min_ovr:
            rows = [r for r in rows if (r["ovr"] or 0) >= args.min_ovr]
        rows = [r for r in rows if _run_parts_ok(r, args)]
        sort_key = {"vilje": lambda r: r["run_ai"].get("decision") or 0, "iq": lambda r: r["run_ai"].get("decision") or 0,
                    "effekt": lambda r: r["run_ai"].get("execution") or 0,
                    "stopp": lambda r: (r.get("hard_to_stop") or {}).get("score") or 0}.get(args.sorter)
        if sort_key is None:
            sort_key = (lambda r: r["run_ai"]["score"]) if args.alle else (lambda r: r["by_group"][g]["run"]["res"])
        rows.sort(key=sort_key, reverse=True)
        sort_names = {"iq": "Løps-IQ", "vilje": "Løps-IQ", "effekt": "løpseffekt", "stopp": "vanskelig å stoppe"}
        what = f"sortert etter {sort_names.get(args.sorter, args.sorter)}" if args.sorter else "alle, sortert etter Løps-AI" if args.alle else (
            f"løper bedre enn {100 - gem['max_res_top_pct']} % av kortene sammenlignet med samme OVR")
        print(f"\n{group_label(g).upper()}: {len(rows)} av {len(pool)} {GROUP_PLURAL_NO[g]} ({what})")
        if len(pool) < gem["min_pool_size"]:
            print(f"  For få {GROUP_PLURAL_NO[g]} til å merke perler (trenger {gem['min_pool_size']}). Bruk --alle.")
        head = (f"{'#':>4}  {'Spiller':<38} {'OVR':>3}  {'Løps-AI':>7} {'IQ':>6} {'Effekt':>6} {'Stopp':>6} {'Plass':>12} {'mot samme OVR':>13}  "
                f"{'Arb.rate':<8} {'Kropp':<15} {'Løfter mest'}")
        print(head)
        print("-" * len(head))
        for i, r in enumerate(rows[:args.top], 1):
            run, ra = r["by_group"][g]["run"], r["run_ai"]
            top = ", ".join(f"{FEATURE_LABELS.get(k, k)} {v}" for k, v, _ in run.get("up", []))
            print(f"{i:>4}  {_fmt(_display_name(r, run_group(r, [g]) != r.get('position_group')), 38)} "
                  f"{_fmt(r['ovr'], 3)}  {ra['score']:>7.1f} {_fmt(ra.get('decision'), 6)} {_fmt(ra.get('execution'), 6)} "
                  f"{_fmt((r.get('hard_to_stop') or {}).get('score'), 6)} "
                  f"{('#' + str(run['rank']) + '/' + str(run['of'])):>12} {run['res']:>+13.1f}  "
                  f"{ra['wr']:<8} {ra['body']:<15} {top}")
    return 0


from .schema import GROUP_PLURAL_NO as GROUP_PLURAL_NO_ALL


def _run_parts_ok(r: dict, args) -> bool:
    """--min-iq (--min-vilje) / --min-effekt: Løps-IQ and Løpseffekt at least this high."""
    ra = r.get("run_ai") or {}
    for want, key in ((getattr(args, "min_vilje", None), "decision"), (getattr(args, "min_effekt", None), "execution")):
        if want is not None and (ra.get(key) is None or ra[key] < want):
            return False
    return True


HORIZON_ARGS = {"na": "live", "nå": "live", "live": "live", "s2": "s2", "s4": "s4", "aar": "aar", "år": "aar", "slutt": "aar"}


def cmd_evolab(args) -> int:
    """Rank cards by how good they can become through evolutions, or show the full plan for one card."""
    from . import evolab
    cfg, players, results = _ranked(args.files)
    lab = evolab.load_lab_config()
    run = evolab.run(players, results, cfg, lab=lab)
    summ = evolab.summarize(run, players, results, cfg)
    hz = evolab.horizons(lab)
    want = HORIZON_ARGS.get((args.horisont or "aar").lower(), "aar")
    hi = next((i for i, h in enumerate(hz) if h["key"] == want), len(hz) - 1)
    by_uid = {r["uid"]: r for r in results}
    if args.name:
        hits = _name_matches([by_uid[u] for u in summ if u in by_uid], args.name, key=lambda r: r["name"])
        if not hits:
            print(f"Fant ingen kort som kan evolueres og matcher '{args.name}'.")
            return 1
        for r in hits[:6]:
            _print_lab_card(r, summ[r["uid"]], hz, hi)
        return 0
    groups = [args.group.upper()] if args.group else [g for g in GROUP_ORDER]
    keyf = {"forventet": lambda s: s["h"][hi]["p50"], "tak": lambda s: s["h"][hi]["p90"],
            "op": lambda s: (s["h"][hi]["op"], s["h"][hi]["p50"]), "gevinst": lambda s: s["h"][hi]["p50"] - s["now"],
            "dna": lambda s: s["dna"]["pts"], "sikker": lambda s: (-(s["h"][hi]["p90"] - s["h"][hi]["p10"]), s["h"][hi]["p50"])}[args.sorter]
    from .schema import GROUP_PLURAL_NO
    print(f"Horisont: {hz[hi]['name']} ({hz[hi]['when']}). OVR {args.min_ovr or 'alle'}-{args.maks_ovr or 'alle'}.")
    for g in groups:
        rows = []
        for uid, s in summ.items():
            r = by_uid.get(uid)
            if not r or s["g"] != g:
                continue
            if args.maks_ovr and (r["ovr"] or 0) > args.maks_ovr or args.min_ovr and (r["ovr"] or 0) < args.min_ovr:
                continue
            if args.bare_live and not s["live"]["steps"]:
                continue
            rows.append((keyf(s), r, s))
        if not rows:
            continue
        rows.sort(key=lambda t: t[0], reverse=True)
        print(f"\n{group_label(g).upper()} ({len(rows)} {GROUP_PLURAL_NO[g]})")
        head = (f"{'#':>4}  {'Spiller':<36} {'OVR':>8}  {'IGR nå':>6} {'P10':>5} {'P50':>5} {'P90':>5}  {'OP':>4}  {'OP fra':<13} "
                f"{'DNA':>9} {'Tilgang':>7}  Evo-plan nå")
        print(head)
        print("-" * len(head))
        for i, (_, r, s) in enumerate(rows[:args.top], 1):
            h = s["h"][hi]
            when = hz[s["when"]]["name"] if s["when"] is not None else "-"
            plan = " > ".join(st["name"] for st in s["live"]["steps"]) or "-"
            print(f"{i:>4}  {_fmt(_display_name(r, False) + (' ~' if s['coarse'] else ''), 36)} {str(r['ovr']) + '->' + str(h['ovr']):>8}  "
                  f"{s['now']:>6.1f} {h['p10']:>5.1f} {h['p50']:>5.1f} {h['p90']:>5.1f}  {h['op']:>3} %  {when:<13} "
                  f"{_top_txt(s['dna']['top']):>9} {(str(s['access']) + ' %') if s['access'] is not None else '-':>7}  {plan[:70]}")
    print("\n~ = grovt anslag (færre simulerte fremtider). Full plan for ett kort: --name NAVN. Siden: output/evolab.html etter rate.")
    return 0


def _top_txt(p: float) -> str:
    return "topp <1 %" if p < 1 else f"topp {round(p)} %"


def _print_lab_card(r: dict, s: dict, hz: list, hi: int) -> None:
    from .evolab import BLOCK_WORDS, attr_label
    from .schema import GROUP_PLURAL_NO
    print(f"\n{_display_name(r, False)}  OVR {r['ovr']}  {group_label(s['g'])}  IGR i dag {s['now']:.1f} "
          f"(#{s['rank_now']} av {s['h'][0]['of']} {GROUP_PLURAL_NO.get(s['g'], '')})" + ("  [grovt anslag]" if s["coarse"] else ""))
    for i, h in enumerate(s["h"]):
        mark = "*" if i == hi else " "
        print(f" {mark} {hz[i]['name']:<15} P50 {h['p50']:>5.1f}  (P10 {h['p10']:.1f} - P90 {h['p90']:.1f})  OVR {h['ovr']}  "
              f"OP-sjanse {h['op']} %  #{h['rank']}")
    lv = s["live"]
    print("  Evo-plan nå:" if lv["steps"] else "  Evo-plan nå: ingen live-evoer passer")
    for n, st in enumerate(lv["steps"], 1):
        top = ", ".join(f"{attr_label(k)} {b}->{a}" for k, b, a in st["d"][:4])
        extra = ", ".join([f"+{x}" for x in st.get("ps", [])] + [f"+{x}+" for x in st.get("psp", [])])
        print(f"    {n}. {st['name']}{' (' + st['path'] + ')' if st.get('path') else ''} [{st['cost']}]  OVR {st['ovr'][0]}->{st['ovr'][1]}"
              f"  {top}{'; ' + extra if extra else ''}")
        for kind, text, good in st.get("gates", []):
            print(f"       {'Terskel' if good else 'FELLE'}: {text}")
    if lv.get("roles"):
        print(f"    {len(lv['steps']) + 1}. Roles++ for hovedposisjonen")
    for t in lv.get("tips", []):
        print(f"  Rekkefølge: {t}")
    for a, b in lv.get("skip", []):
        print(f"  Ikke med: {a}: {b}")
    for a, b in lv.get("near", []):
        print(f"  Nesten: {a}: {b}")
    for a, b in lv.get("chk", []):
        print(f"  Sjekk selv: {a}: {b}")
    alt = lv.get("alt") or {}
    for metric, word in (("run", "løp uten ball"), ("feel", "følelse"), ("stp", "vanskelig å stoppe")):
        if alt.get(metric):
            names = " > ".join(k for k, _ in alt[metric]["seq"])
            print(f"  Best for {word}: {names} ({word} {alt[metric][metric]}, IGR {alt[metric]['igr']})")
    runs = s.get("runs") or {}
    if s.get("runcard"):
        n, l, e = runs.get("now") or [None] * 3, runs.get("live") or [None] * 3, runs.get("end") or [None] * 3
        print(f"  Løps-AI: {n[0]} i dag -> {l[0]} nå -> {e[0]} etter evo (Løps-IQ {n[1]} -> {e[1]}, Effekt {n[2]} -> {e[2]})")
    med = s.get("med") or {}
    if med.get("feel") is not None:
        print(f"  Følelse: {r.get('feel')} -> {lv.get('feel')} nå -> {med['feel']} etter evo")
    if med.get("d"):
        print("  Evoene fikser (typisk fremtid): " + ", ".join(f"{attr_label(k)} {b}->{a}" for k, b, a in med["d"][:8]))
    if med.get("acc") and med.get("acc") != r.get("accelerate"):
        print(f"  AcceleRATE: {r.get('accelerate')} -> {med['acc']}")
    print(f"  Låst DNA: {_top_txt(s['dna']['top'])} (" + ", ".join(c[0] + (f" {c[1]:+.1f}" if c[1] is not None else "") for c in s["dna"]["chips"]) + ")")
    if s.get("access") is not None:
        print(f"  Evo-tilgang: {s['access']} % av evoene kortet har OVR til" +
              ("; stengt av " + ", ".join(f"{BLOCK_WORDS.get(k, k)} {p} %" for k, p in s["block"]) if s["block"] else ""))
    if s.get("fav"):
        print("  Ligner favorittene etter evo: " + ", ".join(f"{n} {p} %" for n, p in s["fav"]))
    if s.get("like"):
        print(f"  Til slutt på nivå med: {s['like'][0]} {s['like'][1]}")


def cmd_evo_import(args) -> int:
    from . import evo_import
    from .evolab import user_evos_path
    text = Path(args.textfile).read_text(encoding="utf-8")
    evo = evo_import.parse(text, name=args.navn, key=args.nokkel)
    for line in evo_import.describe(evo):
        print(line)
    if not evo["req"] and not evo["up"]:
        print("Fant verken krav eller oppgraderinger i teksten. Ingenting lagret.")
        return 1
    if args.vis:
        return 0
    n = evo_import.save(evo, user_evos_path(), until=args.til, cost=args.kostnad)
    print(f"Lagret i {user_evos_path()} ({n} egne evoer). Kjør rate på nytt for å oppdatere Evo Lab.")
    return 0


def cmd_evo_sjekk(args) -> int:
    """Check an evo file (default data/auto_evoer.json) for mistakes before it is committed."""
    from . import evolab
    path = Path(args.fil) if args.fil else evolab.auto_evos_path()
    if not path.exists():
        print(f"{path} finnes ikke. Ingenting å sjekke.")
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as exc:
        print(f"{path} er ikke gyldig JSON: {exc}")
        return 1
    items = data.get("evos", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        print("Filen må ha formatet {\"evos\": [ ... ]}.")
        return 1
    with open(ROOT / "config" / "playstyles.json", encoding="utf-8") as f:
        names = set(json.load(f)["playstyles"]) | {"1v1 Close Down"}
    seen, bad, now = set(), 0, datetime.now(timezone.utc)
    for e in items:
        probs = evolab.check_evo(e, min_sources=args.min_kilder, playstyles=names) if isinstance(e, dict) else ["er ikke et objekt"]
        key = e.get("key", "?") if isinstance(e, dict) else "?"
        if key in seen:
            probs.append("samme key finnes to ganger")
        seen.add(key)
        end = None
        try:
            end = evolab.until_utc(e.get("until")) if isinstance(e, dict) else None
        except (ValueError, TypeError):
            pass
        state = "stengt" if end and end <= now else "åpen"
        print(f"{'FEIL' if probs else 'ok  '} {key} ({state}, til {e.get('until') if isinstance(e, dict) else '?'})")
        for p in probs:
            print(f"      {p}")
        bad += bool(probs)
    print(f"{len(items)} evoer, {bad} med feil.")
    return 1 if bad else 0


def cmd_brukt(args) -> int:
    """List, add or remove evos you have used up on other cards."""
    from .evolab import load_lab_config, load_used, save_used, used_evos_path
    lab = load_lab_config()
    known = {e["key"]: e["name"] for e in lab.get("live", [])}
    used = set(load_used())

    def find(name: str) -> str:
        n = name.strip().lower()
        hits = [k for k, v in known.items() if n in (k.lower(), v.lower())] or \
               [k for k, v in known.items() if n in v.lower() or n in k.lower()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            print(f"  '{name}' passer flere: {', '.join(known[h] for h in hits)}. Skriv mer av navnet.")
            return ""
        print(f"  Fant ingen evo som heter '{name}'. Lagrer navnet som det står.")
        return n
    if args.tom:
        used = set()
    for name in args.evoer or []:
        k = find(name)
        if k:
            used.add(k.lower())
    for name in args.fjern or []:
        k = find(name)
        used.discard(k.lower())
        used.discard(name.strip().lower())
    if args.tom or args.evoer or args.fjern:
        save_used(sorted(used))
    if used:
        print("Brukt opp (Evo Lab og rapporten regner uten disse):")
        for k in sorted(used):
            print(f"  {known.get(k, k)}")
        print(f"Lagret i {used_evos_path()}. Kjør rate på nytt for å oppdatere sidene.")
    else:
        print("Ingen evoer er merket som brukt.")
    return 0


def cmd_test_par(args) -> int:
    """Save one blind A-vs-B test."""
    from . import validate
    cfg, players, results = _ranked(args.files)
    a, ah = validate.find_card(results, args.a, args.versjon_a)
    b, bh = validate.find_card(results, args.b, args.versjon_b)
    for spec, card, hits in ((args.a, a, ah), (args.b, b, bh)):
        if not card:
            print(f"Fant ikke '{spec}'.")
            return 1
        if len({h.get('rarity') for h in hits}) > 1:
            print(f"  {spec}: valgte {card['name']} [{card.get('rarity')}]. Bruk --versjon-a/--versjon-b for en annen versjon.")
    g = validate.common_group(a, b, (args.posisjon or "").upper() or None)
    if not g:
        print("Kortene har ingen felles posisjon.")
        return 1
    n = validate.add_test({"dato": validate.today(), "a": a["name"], "a_versjon": a.get("rarity") or "", "b": b["name"],
                           "b_versjon": b.get("rarity") or "", "vinner": args.vinner, "styrke": args.styrke,
                           "type": args.type, "posisjon": g, "notat": args.notat or ""})
    ia, ib = a["by_group"][g]["igr"], b["by_group"][g]["igr"]
    agree = "lik" if args.vinner == "lik" else ("enig" if (ia > ib) == (args.vinner == "a") else "uenig")
    print(f"Lagret test nr. {n}: {a['name']} (IGR {ia}) mot {b['name']} (IGR {ib}) som {group_label(g)}. Vinner: {args.vinner}. "
          f"IGR er {agree} med deg.")
    return 0


def cmd_evaluer(args) -> int:
    """How well the model agrees with your blind tests."""
    from . import validate
    cfg, players, results = _ranked(args.files)
    tests = validate.load_tests(Path(args.fil) if args.fil else validate.TEST_FILE)
    for line in validate.report_lines(validate.evaluate(tests, results)):
        print(line)
    return 0


def cmd_kombo(args) -> int:
    """Rank cards in a position by the average of their places in the chosen categories."""
    from .profile import category_pools, combo_score, parse_categories
    cfg, _, results = _ranked(args.files)
    chosen = parse_categories(args.kat, cfg)
    labels = {k: c["label"] for k, c in cfg["weights"]["profile"]["categories"].items() if not k.startswith("_")}
    pools = category_pools(results)
    groups = [args.group.upper()] if args.group else [g for g in GROUP_ORDER if g != "GK"]
    for g in groups:
        rows = []
        for r in results:
            if g not in r["by_group"] or (args.min_ovr and (r["ovr"] or 0) < args.min_ovr):
                continue
            if not _run_parts_ok(r, args):
                continue
            if not args.group and (r.get("position_group") != g):
                continue  # without --group: each card in its own position
            sc = combo_score(r, g, chosen, pools)
            if sc is not None:
                rows.append((sc, r))
        if not rows:
            continue
        rows.sort(key=lambda t: t[0], reverse=True)
        from .schema import GROUP_PLURAL_NO
        print(f"\n{group_label(g).upper()}: {' + '.join(labels[k] for k in chosen)} ({len(rows)} {GROUP_PLURAL_NO[g]})")
        short = {"Vanskelig å stoppe": "Stopp"}
        cols = "".join(f" {short.get(labels[k], labels[k])[:10]:>10}" for k in chosen)
        head = f"{'#':>4}  {'Spiller':<38} {'OVR':>3} {'IGR':>5} {'Kombo':>6}{cols}  Stil"
        print(head)
        print("-" * len(head))
        for i, (sc, r) in enumerate(rows[:args.top], 1):
            cats = r["profile"]["cats"]
            vals = "".join(f" {cats[k]:>10.1f}" for k in chosen)
            print(f"{i:>4}  {_fmt(_display_name(r, False), 38)} {_fmt(r['ovr'], 3)} {r['by_group'][g]['igr']:>5.1f} "
                  f"{sc:>6.1f}{vals}  {r['profile'].get('style', '')}")
    return 0


def cmd_lignende(args) -> int:
    """Cards with the most similar run profile to one or more reference cards
    (several names = cards that resemble all of them)."""
    from .runs import run_group, similar_to_all, similarity_pct
    cfg, _, results = _ranked(args.files)
    rc_groups = cfg["weights"]["run_ai"]["groups"]
    refs = []
    for name in args.name:
        found = sorted(_name_matches([r for r in results if r.get("run_ai")], name, key=lambda r: r["name"]),
                       key=lambda r: r["ovr"] or 0, reverse=True)
        if args.versjon:
            found = [r for r in found if args.versjon.lower() in (r.get("rarity") or "").lower()] or found
        if not found:
            print(f"Fant ingen spiss, kant eller CAM som heter '{name}'.")
            return 1
        ref = found[0]
        if len(found) > 1:
            others = ", ".join(_display_name(r, False) for r in found[1:4])
            print(f"'{name}': bruker {_display_name(ref, False)} (også: {others}). Bruk --versjon for et annet kort.")
        refs.append(ref)
        ra = ref["run_ai"]
        print(f"Referanse: {_display_name(ref, False)}, OVR {ref['ovr']}, Løps-AI {ra['score']} "
              f"(IQ {_fmt(ra.get('decision'), 4)}, effekt {_fmt(ra.get('execution'), 4)}), {ra['body']}"
              + (f", {ref['height_cm']:.0f} cm" if ref.get("height_cm") else ""))
    if args.group and args.group.lower() == "alle":
        group = None
    elif args.group:
        group = args.group.upper()
    else:
        own = {run_group(r, rc_groups) for r in refs}
        group = own.pop() if len(own) == 1 else None
    print(f"\nLeter blant {GROUP_PLURAL_NO_ALL.get(group, 'alle spisser, kanter og CAM-er')}"
          + ("" if args.group else " (--group alle for alle)")
          + (f", kort som ligner alle {len(refs)}" if len(refs) > 1 else ""))
    hits = similar_to_all(refs, results, cfg, n=args.top, group=group)
    head = (f"{'#':>3}  {'Spiller':<40} {'Likhet':>6}  {'OVR':>3}  {'Løps-AI':>7} {'Følelse':>7} {'mot samme OVR':>13}  "
            f"{'Posisjoner':<14} {'Kropp':<15}")
    print(head)
    print("-" * len(head))
    for i, (r, d) in enumerate(hits, 1):
        g = run_group(r, [group] if group else rc_groups)
        print(f"{i:>3}  {_fmt(_display_name(r, False), 40)} {similarity_pct(d):>5} %  {_fmt(r['ovr'], 3)}  "
              f"{r['run_ai']['score']:>7.1f} {_fmt(r.get('feel'), 7)} {r['by_group'][g]['run']['res']:>+13.1f}  "
              f"{_fmt('/'.join(r['positions']), 14)} {r['run_ai']['body']:<15}")
    return 0


_TEMPLATE = """navn;versjon;løp;unødvendige;frie;notat
Geyse;FC 25;9;1;5;eksempel, slett denne linjen
Erling Haaland;;4;0;3;eksempel, tom versjon = basekortet
"""


def _read_fasit(path: Path) -> List[dict]:
    import csv
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    rows = []
    for row in csv.DictReader(text.splitlines(), dialect=dialect):
        low = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
        name = low.get("navn") or low.get("name") or low.get("spiller")
        raw = low.get("løp") or low.get("lop") or low.get("runs") or low.get("vurdering") or low.get("score")
        if not name or raw is None or raw == "":
            continue
        words = {"bra": 1, "god": 1, "ja": 1, "dårlig": 0, "darlig": 0, "nei": 0}
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            if raw.lower() not in words:
                print(f"  Hopper over {name}: '{raw}' er ikke et tall eller bra/dårlig")
                continue
            value = float(words[raw.lower()])
        def num(*keys):
            raw_v = next((low[k] for k in keys if low.get(k)), "")
            try:
                return float(raw_v.replace(",", ".")) if raw_v else None
            except ValueError:
                return None
        free = num("frie", "fri", "free")
        waste = num("unødvendige", "unodvendige", "unødvendig", "unodvendig", "bortkastet", "wasted")
        rows.append({"name": name, "version": low.get("versjon") or low.get("version") or "", "label": value,
                     "free": free, "waste": waste})
    return rows


def _match(row: dict, results: List[dict]) -> Optional[dict]:
    from .promo import norm_name
    want = norm_name(row["name"])
    cands = [r for r in results if r.get("run_ai") and want in norm_name(r["name"])]
    v = row["version"].lower().strip()
    if v in ("", "gull", "gold", "basis", "base", "vanlig", "rare", "common"):
        base = [r for r in cands if not r.get("status")]
        cands = base or cands
    else:
        cands = [r for r in cands if v in (r.get("rarity") or "").lower()]
    return max(cands, key=lambda r: r["ovr"] or 0) if cands else None


def _print_calibration(res: dict, what: str, score_name: str) -> None:
    from .runs import FEATURE_LABELS
    print(f"Hvilke tall henger sammen med {what} (+1 = jo høyere tall, jo mer; 0 = ingen sammenheng):")
    for k, (c, n) in sorted(res["corr"].items(), key=lambda kv: kv[1][0], reverse=True):
        bar = "#" * int(abs(c) * 20)
        print(f"  {FEATURE_LABELS.get(k, k):<22} {c:+.2f}  {bar}" + (f"  (bare {n} kort har verdien)" if n < res["n"] else ""))
    print(f"Hvor godt rekkefølgen treffer (1 = perfekt):  OVR {res['corr_ovr']}  ·  {score_name} nå {res['corr_now']}"
          + (f"  ·  kalibrert {res['corr_new_loo']} (testet på kort den ikke ble tilpasset til)"
             if res["corr_new_loo"] is not None else ""))
    if res.get("kept"):
        print("  Kalibrerte vekter traff ikke bedre enn dagens på kort de ikke så, så dagens vekter beholdes her.")


def cmd_kalibrer(args) -> int:
    """Fit Løps-AI to runs you have counted yourself. The two parts are fitted separately
    when there is enough data: Løps-IQ against the share of sensible runs (runs minus
    'unødvendige', divided by runs) or, without that column, against runs started, and
    Løpseffekt against the share of runs where the player got free ('frie')."""
    from .runs import FEATURE_LABELS, calibrate, decision_keys, save_calibration
    fasit = Path(args.fasit)
    if not fasit.exists():
        fasit.parent.mkdir(parents=True, exist_ok=True)
        fasit.write_text(_TEMPLATE, encoding="utf-8")
        print(f"Laget en mal i {fasit}. Fyll inn kortene du har testet og kjør kommandoen igjen.")
        print("  løp         = antall løp bak backlinja spilleren startet på 5 minutter (eller 1-5, eller bra/dårlig)")
        print("  unødvendige = løp som ikke ga noe: offside, løp bort fra spillet, løp når laget trengte støtte (kan stå tom)")
        print("  frie        = hvor mange av løpene der han kom fri eller fikk en sjanse (kan stå tom)")
        return 0
    cfg, _, results = _ranked(args.files)
    rows, missing = [], []
    for row in _read_fasit(fasit):
        r = _match(row, results)
        (rows.append((r, row)) if r else missing.append(row))
    for row in missing:
        print(f"  Fant ikke {row['name']}{' (' + row['version'] + ')' if row['version'] else ''} blant spiss/kant/CAM i filene")
    if len(rows) < 4:
        print(f"Trenger minst 4 kort som finnes i filene (har {len(rows)}).")
        return 1
    print(f"\n{len(rows)} kort fra {fasit.name}:")
    for r, row in sorted(rows, key=lambda t: t[1]["label"], reverse=True):
        ra = r["run_ai"]
        free = f"  fri {row['free']:g}" if row["free"] is not None else ""
        waste = f"  unødv. {row['waste']:g}" if row["waste"] is not None else ""
        print(f"  løp {row['label']:>4g}{waste:<11}{free:<9} {_fmt(_display_name(r, False), 38)} OVR {r['ovr']}  Løps-AI {ra['score']:.1f}"
              f" (IQ {_fmt(ra.get('decision'), 4)}, effekt {_fmt(ra.get('execution'), 4)})")

    rc = cfg["weights"]["run_ai"]
    old = {k: v for k, v in rc["weights"].items() if not k.startswith("_")}
    runs = [(r, row["label"]) for r, row in rows]
    share = [(r, row["free"] / row["label"]) for r, row in rows if row["free"] is not None and row["label"] > 0]
    sensible = [(r, max(0.0, row["label"] - row["waste"]) / row["label"]) for r, row in rows
                if row["waste"] is not None and row["label"] > 0]
    if len(share) >= 4 or len(sensible) >= 4:
        dk = [k for k in decision_keys(rc) if k in old]
        ek = [k for k in old if k not in dk]
        s_d, s_e = sum(old[k] for k in dk), sum(old[k] for k in ek)
        if len(sensible) >= 4:
            res_d = calibrate(sensible, cfg, only=dk)
            print("\nLØPS-IQ (hvor og når spilleren løper), sammenlignet med andelen fornuftige løp (løp minus unødvendige):")
            _print_calibration(res_d, "andelen fornuftige løp", "Løps-IQ")
        else:
            res_d = calibrate(runs, cfg, only=dk)
            print("\nLØPS-IQ, sammenlignet med antall løp (fyll inn 'unødvendige' for å måle IQ i stedet for hvor mye han løper):")
            _print_calibration(res_d, "antall løp", "Løps-IQ")
        new = {k: round(res_d["new"][k] * s_d, 3) for k in dk}
        if len(share) >= 4:
            res_e = calibrate(share, cfg, only=ek)
            print("\nLØPSEFFEKT (om løpet skaper avstand), sammenlignet med andelen løp der han kom fri:")
            _print_calibration(res_e, "andelen frie løp", "Løpseffekt")
            new.update({k: round(res_e["new"][k] * s_e, 3) for k in ek})
        else:
            new.update({k: old[k] for k in ek})
            print("  (Fyll inn 'frie' for minst 4 kort for å kalibrere Løpseffekt også.)")
        n = len(runs)
    else:
        res = calibrate(runs, cfg)
        print()
        _print_calibration(res, "løpene dine", "Løps-AI")
        new, n = res["new"], res["n"]
        if any(row["free"] is not None or row["waste"] is not None for _, row in rows):
            print("  (Fyll inn 'unødvendige' og 'frie' for minst 4 kort for å kalibrere Løps-IQ og Løpseffekt hver for seg.)")
    print("\nVekter (nå -> kalibrert):")
    for k in old:
        print(f"  {FEATURE_LABELS.get(k, k):<22} {old[k]:.3f} -> {new.get(k, old[k]):.3f}")
    if n < 10:
        print(f"\nMerk: {n} kort er lite. Med under 10 kort flyttes vektene bare litt. Test flere for sikrere svar.")
    if args.lagre:
        path = save_calibration(new, n, ROOT / "config")
        print(f"\nLagret i {path}. Neste 'rate' bruker de kalibrerte vektene. Slett filen for å gå tilbake.")
    else:
        print("\nKjør med --lagre for å bruke de kalibrerte vektene.")
    return 0


def cmd_import_text(args) -> int:
    text = Path(args.textfile).read_text(encoding="utf-8")
    plus, base = local_src.split_playstyles(args.ps or [])
    roles = {}
    for spec in args.role or []:
        pos, role, level = (spec.split(":") + ["0"])[:3]
        roles.setdefault(pos.upper(), {})[role] = int(level)
    player = local_src.player_from_text(
        text, args.name, args.position.upper(),
        alt_positions=[a.upper() for a in args.alt or []], gender=args.gender,
        height_cm=args.height, weight_kg=args.weight, weak_foot=args.wf, skill_moves=args.sm,
        ovr=args.ovr, playstyles_plus=plus, playstyles=base, roles=roles,
        roles_complete=bool(roles), playstyles_complete=bool(args.ps), rarity=args.rarity,
        source=f"tekst:{Path(args.textfile).name}",
    )
    found = len(player.attributes)
    print(f"Fant {found} attributter for {player.name}.")
    if found < 25:
        print("  Advarsel: få attributter funnet. Sjekk at du kopierte hele spillersiden.")
    out = Path(args.out)
    existing = local_src.load_json(str(out)) if out.exists() else []
    existing = [p for p in existing if p.name != player.name]
    existing.append(player)
    local_src.save_json(existing, str(out))
    print(f"Lagret i {out} ({len(existing)} spillere).")
    return 0


def _keep_heights(players: List[Player], old_file: str) -> int:
    """EA's FC 27 pages leave height and weight empty. Keep them from the previous file (same EA id)."""
    if not Path(old_file).exists():
        return 0
    try:
        old = {str(p.id): p for p in local_src.load_any(old_file) if p.id}
    except Exception:  # an unreadable old file should not stop a fresh fetch
        return 0
    n = 0
    for p in players:
        o = old.get(str(p.id))
        if not o:
            continue
        changed = False
        if p.height_cm is None and o.height_cm:
            p.height_cm, changed = o.height_cm, True
        if getattr(p, "weight_kg", None) is None and getattr(o, "weight_kg", None):
            p.weight_kg, changed = o.weight_kg, True
        n += changed
    return n


def cmd_fetch_ea(args) -> int:
    from .sources import ea_ratings
    cfg = ea_ratings.load_sources_config()
    if args.dump_sample:
        ea = cfg["ea_ratings"]
        if not ea.get("url_template"):
            print("url_template mangler i config/sources.json.")
            return 1
        data = ea_ratings._get(ea["url_template"].format(offset=0, limit=1, page=0), ea["user_agent"])
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        sample = Path(args.out).with_name("ea_sample.json")
        sample.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Lagret ett rått svar i {sample}")
        return 0
    meta_path = Path(args.out).with_name(Path(args.out).stem + ".meta.json")
    source = "ea-ratingsider-4" if cfg["ea_ratings"].get("html_url_template") else "drop-api"
    if args.hvis_gammel is not None and Path(args.out).exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["fetched"])).total_seconds() / 86400
            if meta.get("source") == source and age < args.hvis_gammel:
                print(f"EA-dataene er {age:.1f} dager gamle (henter på nytt etter {args.hvis_gammel}). Hopper over.")
                return 0
        except (ValueError, KeyError):
            pass
    print("Henter EAs ratingdatabase ...")
    players = ea_ratings.fetch_all(cfg, max_pages=args.max_pages, raw_dir=args.raw_dir)
    if len(players) < 1000 and not args.max_pages:
        print(f"Fikk bare {len(players)} spillere fra EA. Beholder filen fra forrige gang.")
        return 1
    kept = _keep_heights(players, args.out)
    if kept:
        print(f"  Høyde og vekt mangler hos EA for FC 27; tok dem fra forrige fil for {kept} spillere.")
    local_src.save_json(players, args.out)
    meta_path.write_text(json.dumps({"source": source, "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "players": len(players)}, ensure_ascii=False), encoding="utf-8")
    alts = sum(1 for p in players if p.alt_positions)
    print(f"Lagret {len(players)} spillere i {args.out} ({alts} med alternative posisjoner)")
    return 0


def _specials(cfg_src: dict, full=None, detail_limit=None, leaks=True, fifarosters=True,
              base_file: Optional[str] = None, include_base: bool = False, offline: bool = False,
              promos: Optional[List[str]] = None) -> Optional[str]:
    """Fetch (unless offline) and build special cards. Returns the output file path."""
    from . import specials
    from .sources import fifarosters as fr
    from .sources import realsport101 as rs
    cache_dir = str(ROOT / "data" / "cache")
    if offline:
        fr_cache = fr.FifaRostersCache(str(Path(cache_dir) / "fifarosters")) if fifarosters else None
        leak_cache = rs.LeakCache(str(Path(cache_dir) / "realsport101")) if leaks else None
    else:
        base_path0 = Path(base_file) if base_file else ROOT / "data" / "ea_players.json"
        known = {str(p.id) for p in local_src.load_any(str(base_path0)) if p.height_cm} if base_path0.exists() else set()
        fr_cache, leak_cache = specials.run_fetch(cfg_src, cache_dir, full=full, detail_limit=detail_limit,
                                                  leaks=leaks, fifarosters=fifarosters, extra_promos=promos,
                                                  height_known=known)
        fr_cache = fr_cache if fifarosters else None
        leak_cache = leak_cache if leaks else None
    base_path = Path(base_file) if base_file else ROOT / "data" / "ea_players.json"
    base = local_src.load_any(str(base_path)) if base_path.exists() else []
    if not base:
        print(f"Merk: fant ikke basekort i {base_path}. Kjør fetch-ea først, ellers kan bare kort "
              "med egen kortside bygges.")
    use_base = include_base or bool(cfg_src["specials"]["fifarosters"].get("use_base_cards", True))
    cards, problems = specials.build_specials(base, fr_cache, leak_cache, load_config(), include_base=use_base)
    out = ROOT / cfg_src["specials"]["output"]
    local_src.save_json(cards, str(out))
    leaked = sum(1 for c in cards if c.status == "lekket")
    est = sum(1 for c in cards if c.estimated)
    n_base = sum(1 for c in cards if c.source == specials.FC27_BASE_SOURCE)
    print(f"Kort fra FIFA Rosters og RealSport101: {len(cards)} lagret i {out} ({n_base} FC 27-basekort, "
          f"{len(cards) - n_base} spesialkort, {leaked} lekket, {est} med estimerte attributter)")
    for msg in problems[:10]:
        print(f"  Merk: {msg}")
    if len(problems) > 10:
        print(f"  ... og {len(problems) - 10} til")
    return str(out)


def cmd_fetch_specials(args) -> int:
    from .sources import ea_ratings
    cfg_src = ea_ratings.load_sources_config()
    _specials(cfg_src, full=True if args.full else None, detail_limit=args.detail_limit,
              leaks=not args.no_leaks, fifarosters=not args.no_fifarosters, base_file=args.base,
              include_base=args.include_base, offline=args.offline, promos=args.promo)
    return 0


def cmd_watch(args) -> int:
    from .sources import ea_ratings
    cfg_src = ea_ratings.load_sources_config()
    interval = args.interval or cfg_src["watch"]["interval_minutes"]
    while True:
        stamp = datetime.now().strftime("%H:%M")
        extra = [str(ROOT / f) for f in cfg_src["watch"].get("extra_files", []) if (ROOT / f).exists()]
        files = list(extra)
        ea_file = ROOT / "data" / "ea_players.json"
        if cfg_src["ea_ratings"].get("url_template") or cfg_src["ea_ratings"].get("html_url_template"):
            try:  # EA's base cards change seldom: fetched again after refresh_days
                cmd_fetch_ea(argparse.Namespace(out=str(ea_file), max_pages=None, raw_dir=None, dump_sample=False,
                                                hvis_gammel=float(cfg_src["ea_ratings"].get("refresh_days", 7))))
            except Exception as exc:  # keep running on network errors
                print(f"[{stamp}] Henting fra EA feilet: {exc}")
        if ea_file.exists():
            files.insert(0, str(ea_file))
        if cfg_src["watch"].get("specials", True):
            try:
                out = _specials(cfg_src)
                if out and Path(out).exists():
                    files.append(out)
            except Exception as exc:
                print(f"[{stamp}] Spesialkort feilet: {exc}")
        if not files:
            print("Ingen data å rate. Sjekk config/sources.json.")
            return 1
        rate_args = argparse.Namespace(files=files, chem=args.chem, group=None, top=args.top, out=args.out, uten_evolab=False,
                                       ignorer_brukte=args.publiser)
        print(f"[{stamp}] Rater {', '.join(Path(f).name for f in files)}")
        cmd_rate(rate_args)
        if args.publiser:
            cmd_publiser(argparse.Namespace(fra=args.out, til=None, deploy=args.deploy))
        if args.once:
            return 0
        print(f"Neste oppdatering om {interval} min. Avslutt med Ctrl+C.")
        time.sleep(interval * 60)


def cmd_publiser(args) -> int:
    """Build site/ (what is uploaded) from output/, and upload it to Cloudflare Pages with --deploy."""
    from . import site
    made = site.ensure_user_config()
    if made:
        print(f"Laget {made}. Fyll inn eier og kontakt der før du deler siden.")
    cfg = site.site_config()
    res = site.publish(args.fra, args.til, cfg)
    print(f"Laget {res['dir']} med {len(res['files'])} filer (uten ratings.csv/json og evolab.csv).")
    for w in res["warnings"]:
        print(f"  Merk: {w}")
    if not getattr(args, "deploy", False):
        return 0
    import shutil
    import subprocess
    npx = shutil.which("npx")
    if not npx:
        print("Fant ikke npx. Installer Node.js (nodejs.org) for å laste opp fra PC-en, eller la GitHub gjøre det (se README).")
        return 1
    project = cfg.get("cloudflare_prosjekt") or "fc27-rating"
    cmd = [npx, "--yes", "wrangler", "pages", "deploy", res["dir"], f"--project-name={project}", "--branch=main",
           "--commit-dirty=true"]
    print("Laster opp: " + " ".join(cmd[1:]))
    return subprocess.call(cmd, cwd=str(ROOT))  # from the project folder, so functions/ (password lock) comes along


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fcrating", description="Din egen FC 27 ingame-rating")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rate", help="rate spillere og skriv rapport")
    r.add_argument("files", nargs="+")
    r.add_argument("--chem", default="none", help="none, best eller navnet på en kjemistil")
    r.add_argument("--group", help="ST, W, CAM, CM, CDM, FB, CB eller GK")
    r.add_argument("--top", type=int, default=50)
    r.add_argument("--out", default=str(ROOT / "output"))
    r.add_argument("--uten-evolab", action="store_true", help="hopp over Evo Lab (raskere)")
    r.add_argument("--lagre-meta-start", action="store_true",
                   help="lagre startnivået for Meta hvis det mangler (gjøres av GitHub-jobben første gang)")
    r.add_argument("--ignorer-brukte", action="store_true",
                   help="regn som om ingen evoer er brukt opp (for siden du deler; hver venn huker av sine egne)")
    r.set_defaults(func=cmd_rate)

    el = sub.add_parser("evolab", help="hvor gode kortene kan bli med evoer")
    el.add_argument("files", nargs="+")
    el.add_argument("--maks-ovr", type=int, help="bare kort med høyst denne OVR-en (evoens krav), f.eks. 79")
    el.add_argument("--min-ovr", type=int)
    el.add_argument("--group", help="ST, W, CAM, CM, CDM, FB, CB eller GK")
    el.add_argument("--horisont", default="aar", help="nå, s2, s4 eller aar (resten av året, standard)")
    el.add_argument("--sorter", default="forventet", choices=["forventet", "tak", "op", "gevinst", "dna", "sikker"])
    el.add_argument("--top", type=int, default=15)
    el.add_argument("--name", help="full evo-plan for ett kort")
    el.add_argument("--bare-live", action="store_true", help="bare kort som har en live-evo nå")
    el.set_defaults(func=cmd_evolab)

    tp = sub.add_parser("test-par", help="lagre en blind test: hvilket av to kort spilte best")
    tp.add_argument("files", nargs="+")
    tp.add_argument("--a", required=True, help="kort A (navn, eller 'Navn|Versjon')")
    tp.add_argument("--b", required=True, help="kort B")
    tp.add_argument("--vinner", required=True, choices=["a", "b", "lik"])
    tp.add_argument("--styrke", type=int, default=2, choices=[1, 2, 3], help="1 = litt bedre, 3 = klart bedre")
    tp.add_argument("--type", default="alt", choices=["alt", "ball", "løp", "lop"], help="hva du testet: alt, med ball eller løp uten ball")
    tp.add_argument("--posisjon", help="posisjonen du testet i (ST, W, CAM ...)")
    tp.add_argument("--versjon-a")
    tp.add_argument("--versjon-b")
    tp.add_argument("--notat")
    tp.set_defaults(func=cmd_test_par)

    ev = sub.add_parser("evaluer", help="hvor godt modellen treffer de blinde testene dine")
    ev.add_argument("files", nargs="+")
    ev.add_argument("--fil", help="testfil (standard data/tester.csv)")
    ev.set_defaults(func=cmd_evaluer)

    sj = sub.add_parser("evo-sjekk", help="sjekk evo-filen (data/auto_evoer.json) for feil før den lagres")
    sj.add_argument("fil", nargs="?", help="standard data/auto_evoer.json")
    sj.add_argument("--min-kilder", type=int, default=2, help="minst så mange ulike kilde-lenker per evo (standard 2)")
    sj.set_defaults(func=cmd_evo_sjekk)

    br = sub.add_parser("brukt", help="evoer du har brukt opp på andre kort (Evo Lab regner uten dem)")
    br.add_argument("evoer", nargs="*", help="navn på evoer du har brukt, f.eks. \"Batigol Precision\"")
    br.add_argument("--fjern", nargs="+", help="ta evoer ut av listen igjen")
    br.add_argument("--tom", action="store_true", help="tøm listen")
    br.set_defaults(func=cmd_brukt)

    ei = sub.add_parser("evo-import", help="legg inn en ny evo fra tekst kopiert fra FUTBIN/FUT.GG")
    ei.add_argument("textfile")
    ei.add_argument("--navn", help="navnet på evoen (ellers første linje)")
    ei.add_argument("--nokkel", help="intern nøkkel (ellers laget av navnet)")
    ei.add_argument("--til", help="siste dag evoen er åpen, f.eks. 2026-10-25")
    ei.add_argument("--kostnad", help="f.eks. gratis, 25 000 mynter, premium sesongpass")
    ei.add_argument("--vis", action="store_true", help="bare vis hva som ble lest, ikke lagre")
    ei.set_defaults(func=cmd_evo_import)

    e = sub.add_parser("explain", help="vis full utregning for en spiller")
    e.add_argument("files", nargs="+")
    e.add_argument("--name", required=True)
    e.add_argument("--chem", default="none")
    e.add_argument("--groups", nargs="*")
    e.set_defaults(func=cmd_explain)

    v = sub.add_parser("evo", help="ranger evo-potensial")
    v.add_argument("files", nargs="+")
    v.add_argument("--top", type=int, default=50)
    v.add_argument("--group", help="bare én posisjon: ST, W, CAM, CM, CDM, FB eller CB")
    v.add_argument("--sort", default="etter", choices=["etter", "gevinst"],
                   help="etter = beste IGR etter evo (standard), gevinst = størst økning")
    v.set_defaults(func=cmd_evo)

    pe = sub.add_parser("perler", help="skjulte perler: løps-AI mye bedre enn OVR")
    pe.add_argument("files", nargs="+")
    pe.add_argument("--group", help="ST, W eller CAM")
    pe.add_argument("--top", type=int, default=30)
    pe.add_argument("--alle", action="store_true", help="vis alle sortert etter Løps-AI, ikke bare perlene")
    pe.add_argument("--min-ovr", type=int, help="bare kort med minst denne OVR-en, f.eks. 75")
    pe.add_argument("--min-iq", "--min-vilje", dest="min_vilje", type=float, help="bare kort med minst denne Løps-IQ-en, f.eks. 85")
    pe.add_argument("--min-effekt", type=float, help="bare kort med minst denne løpseffekten, f.eks. 85")
    pe.add_argument("--sorter", choices=["iq", "vilje", "effekt", "stopp"], help="sorter etter Løps-IQ, løpseffekt eller vanskelig å stoppe (bruk med --alle)")
    pe.set_defaults(func=cmd_perler)

    li = sub.add_parser("lignende", help="kort med lignende løpsprofil som et kort du liker")
    li.add_argument("files", nargs="+")
    li.add_argument("--name", required=True, nargs="+",
                    help='ett eller flere navn, f.eks. --name Aimar Pichon (bruk "" rundt navn med mellomrom)')
    li.add_argument("--versjon", help="velg kortversjon, f.eks. Heroes, Icon, Future Stars, TOTW")
    li.add_argument("--group", help="ST, W, CAM eller alle (standard: samme posisjon som referansen)")
    li.add_argument("--top", type=int, default=15)
    li.set_defaults(func=cmd_lignende)

    ko = sub.add_parser("kombo", help="ranger etter en kombinasjon av kategorier, f.eks. følelse løp dribling")
    ko.add_argument("files", nargs="+")
    ko.add_argument("--kat", nargs="+", required=True,
                    help="følelse, fart, løp, iq, effekt, stopp, dribling, avslutning, pasning, fysikk, forsvar")
    ko.add_argument("--group", help="ST, W, CAM, CM, CDM, FB eller CB (uten: hvert kort i sin egen posisjon)")
    ko.add_argument("--top", type=int, default=20)
    ko.add_argument("--min-ovr", type=int)
    ko.add_argument("--min-iq", "--min-vilje", dest="min_vilje", type=float, help="bare kort med minst denne Løps-IQ-en")
    ko.add_argument("--min-effekt", type=float, help="bare kort med minst denne løpseffekten")
    ko.set_defaults(func=cmd_kombo)

    ka = sub.add_parser("kalibrer", help="tilpass Løps-AI til løp du har talt selv")
    ka.add_argument("files", nargs="+")
    ka.add_argument("--fasit", default=str(ROOT / "data" / "loep.csv"),
                    help="CSV med navn;versjon;løp (lages som mal hvis den ikke finnes)")
    ka.add_argument("--lagre", action="store_true", help="lagre de kalibrerte vektene")
    ka.set_defaults(func=cmd_kalibrer)

    t = sub.add_parser("import-text", help="lag spiller fra kopiert sidetekst")
    t.add_argument("textfile")
    t.add_argument("--name", required=True)
    t.add_argument("--position", required=True)
    t.add_argument("--alt", nargs="*")
    t.add_argument("--gender", default="M", choices=["M", "F"])
    t.add_argument("--height", type=float)
    t.add_argument("--weight", type=float)
    t.add_argument("--wf", type=int)
    t.add_argument("--sm", type=int)
    t.add_argument("--ovr", type=int)
    t.add_argument("--rarity")
    t.add_argument("--ps", nargs="*", help='f.eks. "Pinged Pass+" "Technical"')
    t.add_argument("--role", nargs="*", help='f.eks. "ST:Advanced Forward:2" (2 = ++, 1 = +)')
    t.add_argument("--out", default=str(ROOT / "data" / "mine_spillere.json"))
    t.set_defaults(func=cmd_import_text)

    f = sub.add_parser("fetch-ea", help="hent EAs ratingdatabase")
    f.add_argument("--out", default=str(ROOT / "data" / "ea_players.json"))
    f.add_argument("--max-pages", type=int)
    f.add_argument("--raw-dir", default=None)
    f.add_argument("--dump-sample", action="store_true")
    f.add_argument("--hvis-gammel", type=float, metavar="DAGER",
                   help="hent bare hvis filen mangler eller er eldre enn så mange dager (eller fra en annen kilde)")
    f.set_defaults(func=cmd_fetch_ea)

    sp = sub.add_parser("fetch-specials", help="hent Icons, TOTW og kampanjekort (FIFA Rosters) og lekkasjer (RealSport101)")
    sp.add_argument("--full", action="store_true", help="gå gjennom hele FC 27-listen nå (ellers én gang i uka)")
    sp.add_argument("--detail-limit", type=int, help="maks antall kortsider å hente nå")
    sp.add_argument("--no-leaks", action="store_true")
    sp.add_argument("--no-fifarosters", action="store_true")
    sp.add_argument("--include-base", action="store_true", help="ta også med basekort fra FIFA Rosters (reserve hvis EA ikke virker)")
    sp.add_argument("--base", help="fil med basekort (standard data/ea_players.json)")
    sp.add_argument("--offline", action="store_true", help="bygg fra lagrede data uten å hente noe")
    sp.add_argument("--promo", nargs="*", help="ekstra kampanjesider på FIFA Rosters, f.eks. fut-future-stars onestowatch")
    sp.set_defaults(func=cmd_fetch_specials)

    w = sub.add_parser("watch", help="hent og rater automatisk med jevne mellomrom")
    w.add_argument("--interval", type=int, help="minutter mellom hver oppdatering")
    w.add_argument("--once", action="store_true")
    w.add_argument("--chem", default="none")
    w.add_argument("--top", type=int, default=30)
    w.add_argument("--out", default=str(ROOT / "output"))
    w.add_argument("--publiser", action="store_true", help="lag også site/ for vennene dine etter hver runde")
    w.add_argument("--deploy", action="store_true", help="med --publiser: last opp til Cloudflare Pages (trenger Node.js)")
    w.set_defaults(func=cmd_watch)

    pu = sub.add_parser("publiser", help="lag site/ som kan legges ut for vennene dine (uten rådata)")
    pu.add_argument("--fra", default=str(ROOT / "output"), help="mappen rate skrev til")
    pu.add_argument("--til", default=None, help="mappen som lastes opp (standard site/)")
    pu.add_argument("--deploy", action="store_true", help="last opp til Cloudflare Pages med wrangler (trenger Node.js)")
    pu.set_defaults(func=cmd_publiser)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"Feil: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Avsluttet.")
        return 0
    except BrokenPipeError:  # output piped to e.g. head
        return 0
