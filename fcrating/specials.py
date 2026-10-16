"""Collect special cards from FIFA Rosters (released) and RealSport101 (leaks)
and turn them into rated-ready Player records."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from .net import Blocked, PoliteFetcher
from .promo import BaseIndex, build_special, drop_released_leaks, norm_name
from .schema import Player
from .sources import fifarosters as fr
from .sources import futgg
from .sources import realsport101 as rs


FC27_BASE_SOURCE = "FIFA Rosters (FC 27-basekort)"
EA_SOURCE = "ea-ratings"


def prefer_fc27_base(players: List[Player], min_cards: int = 5000) -> Tuple[List[Player], str]:
    """When FC 27 base cards from FIFA Rosters are loaded, the older EA cards are only
    templates (attributes, height, alternative positions, PlayStyles) and are not rated themselves."""
    fc27 = [p for p in players if p.source == FC27_BASE_SOURCE]
    if not fc27:
        return players, ""
    ea = [p for p in players if p.source == EA_SOURCE]
    if len(fc27) >= min_cards:
        kept = [p for p in players if p.source != EA_SOURCE]
        return kept, (f"Basekort: {len(fc27)} FC 27-kort fra FIFA Rosters. De {len(ea)} kortene i EA-filen brukes som mal "
                      "for attributter, høyde, posisjoner og PlayStyles.")
    replaced = {str(p.base_id) for p in fc27 if p.base_id} | {str(p.id) for p in fc27 if p.id}
    kept = [p for p in players if not (p.source == EA_SOURCE and str(p.id) in replaced)]
    return kept, f"Basekort: {len(fc27)} FC 27-kort fra FIFA Rosters erstatter de samme spillerne fra EA-filen."


def _no_base_version(version: str) -> bool:
    v = (version or "").lower()
    return "icon" in v or "hero" in v


def card_key(e: dict) -> tuple:
    """Same player, version, OVR, position and face stats = the same card."""
    who = str(e.get("player_id") or norm_name(e["name"]))
    face = tuple(sorted((k, round(float(v))) for k, v in (e.get("face") or {}).items()))
    return (who, (e.get("version") or "").strip().lower(), e.get("ovr"), e.get("position"), face)


def unique_entries(fr_cache: fr.FifaRostersCache) -> List[Tuple[str, dict]]:
    """FIFA Rosters sometimes lists one card twice under different ids. Keep
    one per card, preferring the copy whose card page (attributes) is fetched."""
    chosen: dict = {}
    for futid, e in fr_cache.entries.items():
        key = card_key(e)
        if key not in chosen or (futid in fr_cache.details and chosen[key][0] not in fr_cache.details):
            chosen[key] = (futid, e)
    return list(chosen.values())


def build_specials(base_players: List[Player], fr_cache: Optional[fr.FifaRostersCache],
                   leak_cache: Optional[rs.LeakCache], cfg: dict,
                   include_base: bool = False) -> Tuple[List[Player], List[str]]:
    index = BaseIndex(base_players)
    out: List[Player] = []
    problems: List[str] = []
    fc27_base: List[Player] = []

    if fr_cache and include_base:
        # FC 27 base cards: OVR, position and face stats from FIFA Rosters; attributes from the
        # card page when fetched, otherwise estimated from the older EA card plus the face-stat change.
        for futid, e in unique_entries(fr_cache):
            if not fr.is_base_version(e["version"]):
                continue
            base, _ = index.find(name=e["name"], player_id=e.get("player_id"), exact_name=True)
            detail = fr_cache.details.get(futid) or {}
            card = build_special(
                base, name=e["name"], version=e["version"], ovr=e["ovr"], face=e["face"], cfg=cfg,
                position=e["position"], attributes=detail.get("attributes") or None,
                status=None, card_id=e.get("player_id") or futid, url=e["url"],
                height_cm=detail.get("height_cm"), skill_moves=e.get("skill_moves"),
                weak_foot=e.get("weak_foot"), source=FC27_BASE_SOURCE,
                work_rates=detail.get("work_rates") or e.get("work_rates"), special=False)
            if card is None:
                continue  # new player without an older EA card or a fetched card page
            fc27_base.append(card)
        # special cards start from the FC 27 base card where there is one
        index = BaseIndex(fc27_base + list(base_players))

    if fr_cache:
        for futid, e in unique_entries(fr_cache):
            if fr.is_base_version(e["version"]):
                continue
            if _no_base_version(e["version"]):
                base = None  # Icons and Heroes have no EA base card; never match a namesake
            else:
                base, _ = index.find(name=e["name"], player_id=e.get("player_id"), exact_name=True)
            detail = fr_cache.details.get(futid) or {}
            card = build_special(
                base, name=e["name"], version=e["version"], ovr=e["ovr"], face=e["face"], cfg=cfg,
                position=e["position"], attributes=detail.get("attributes") or None,
                status="utgitt", card_id=futid, url=e["url"],
                height_cm=detail.get("height_cm"), skill_moves=e.get("skill_moves"),
                weak_foot=e.get("weak_foot"), source="FIFA Rosters",
                work_rates=detail.get("work_rates") or e.get("work_rates"))
            if card is None:
                problems.append(f"{e['name']} ({e['version']}): venter på kortsiden (ingen basekort å bygge fra)")
                continue
            if not base:
                card.playstyles_complete = False
            out.append(card)

    if leak_cache:
        seen = set()
        for c in leak_cache.all_cards():
            key = (norm_name(c["name"]), c["version"].strip().lower(), c["ovr"])
            if key in seen:  # the same leak in several articles
                continue
            seen.add(key)
            base, how = index.find(name=c["name"], max_ovr=c["ovr"])
            if not base:
                problems.append(f"{c['name']} ({c['version']}, lekket): {how}")
                continue
            card = build_special(
                base, name=c["name"], version=c["version"], ovr=c["ovr"], face=c["face"], cfg=cfg,
                ps_plus=c.get("ps_plus", []), status="lekket", card_id=None, url=c.get("url"),
                source="RealSport101")
            if card:
                out.append(card)

    return fc27_base + drop_released_leaks(out), problems


def work_rates_by_player(entries: dict) -> dict:
    """EA player id -> 'H/M' from FIFA Rosters list entries. Base cards first,
    because special cards can have other work rates."""
    out: dict = {}
    for e in entries.values():
        pid, wr = e.get("player_id"), e.get("work_rates")
        if not pid or not wr:
            continue
        if fr.is_base_version(e.get("version", "")) or pid not in out:
            out[str(pid)] = wr
    return out


def load_work_rates(cache_dir: str) -> dict:
    """Read only the list cache (not the large card-page cache)."""
    import json
    path = Path(cache_dir) / "fifarosters" / "kort.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return work_rates_by_player(json.load(f))


def apply_work_rates(players: List[Player], table: dict) -> int:
    """Fill in work rates on cards that lack them (e.g. EA base cards). Returns count."""
    from .schema import split_work_rates
    n = 0
    for p in players:
        if p.work_rate_att:
            continue
        wr = table.get(str(p.id)) or table.get(str(p.base_id))
        att, dfn = split_work_rates(wr)
        if att:
            p.work_rate_att, p.work_rate_def = att, dfn
            n += 1
    return n


def promo_slug(value: str) -> str:
    v = value.strip()
    if v.startswith("http"):
        v = v.rstrip("/").split("/")[-1]
    return v.split("?")[0].replace(".php", "")


def promo_url(value: str) -> str:
    """'fut-future-stars' or a full URL -> list URL template with {page}."""
    v = value.strip()
    if "{page}" in v:
        return v
    return f"https://www.fifarosters.com/{promo_slug(v)}.php?&pageNum={{page}}"


def promo_variants(value: str) -> List[str]:
    """Address forms to try for a promo page; the first that shows FC 27 cards is used."""
    if "{page}" in value:
        return [value.strip()]
    slug, base = promo_slug(value), "https://www.fifarosters.com/"
    v = fr.GAME_VERSION
    return [f"{base}{slug}.php?&pageNum={{page}}", f"{base}{slug}.php?v={v}&pageNum={{page}}",
            f"{base}{slug}?v={v}&pageNum={{page}}", f"{base}{slug}?pageNum={{page}}&v={v}"]


def scan_promo(fetcher, fr_cache: fr.FifaRostersCache, value: str, max_pages: Optional[int], log=print) -> int:
    """Find the address form that lists FC 27 cards for this promo and scan it."""
    name = promo_slug(value)
    for tpl in promo_variants(value):
        url = tpl.format(page=1)
        try:
            html = fetcher.get(url)
        except Blocked:
            raise
        except Exception as exc:
            log(f"  {name}: {url} svarte ikke ({exc})")
            continue
        all_cards = fr.parse_list_page(html, version=None)
        explicit = [e for e in all_cards if f"v={fr.GAME_VERSION}" in (e.get("url") or "")]
        if explicit:  # only trust a page whose card links say FC 27
            before = len(fr_cache.entries)
            found = fr.scan_list(fetcher, fr_cache, tpl, max_pages, log)
            log(f"FIFA Rosters: {name}: {found} FC 27-kort, {len(fr_cache.entries) - before} nye")
            return found
        log(f"  {name}: {url} viste {len(all_cards)} kort, ingen fra FC 27")
    log(f"FIFA Rosters: fant ingen FC 27-kort for {name}. Prøv --full, eller sjekk navnet i adressen på fifarosters.com.")
    return 0


def run_fetch(cfg_sources: dict, cache_dir: str, full: Optional[bool] = None, detail_limit: Optional[int] = None,
              leaks: bool = True, fifarosters: bool = True, log=print,
              extra_promos: Optional[List[str]] = None,
              height_known: Optional[set] = None) -> Tuple[fr.FifaRostersCache, rs.LeakCache]:
    sc = cfg_sources["specials"]
    fetcher = PoliteFetcher(user_agent=sc.get("user_agent") or "fc27-rating/0.2 (personlig bruk)",
                            delay_seconds=float(sc.get("delay_seconds", 2.0)), log=log)
    fr_cache = fr.FifaRostersCache(str(Path(cache_dir) / "fifarosters"))
    leak_cache = rs.LeakCache(str(Path(cache_dir) / "realsport101"))

    if fifarosters:
        frc = sc["fifarosters"]
        last_full = fr_cache.meta.get("last_full_scan")
        due = not last_full or datetime.fromisoformat(last_full) < datetime.now() - timedelta(days=frc["full_scan_days"])
        do_full = due if full is None else full
        try:
            if do_full:
                log("FIFA Rosters: går gjennom hele FC 27-listen (tar en stund første gang) ...")
                fr.scan_list(fetcher, fr_cache, frc["full_list_url"], frc.get("max_pages"), log)
                fr_cache.meta["last_full_scan"] = datetime.now().isoformat(timespec="seconds")
            log("FIFA Rosters: sjekker Team of the Week ...")
            if fr.scan_list(fetcher, fr_cache, frc["totw_list_url"], None, log) == 0:
                log("  Fant ingen kort på TOTW-listen. Har FIFA Rosters endret oppsett? Se README.")
            promos = list(frc.get("promo_list_urls") or []) + list(extra_promos or [])
            for raw in dict.fromkeys(promos):
                scan_promo(fetcher, fr_cache, raw, frc.get("promo_max_pages", 20), log)
            specials = [fid for fid, e in unique_entries(fr_cache) if not fr.is_base_version(e["version"])]
            # newest cards first is not known, so take the highest rated first
            specials.sort(key=lambda fid: fr_cache.entries[fid]["ovr"], reverse=True)
            limit = frc["detail_limit_per_run"] if detail_limit is None else detail_limit
            n = fr.fetch_details(fetcher, fr_cache, specials, limit, log)
            missing = sum(1 for fid in specials if fid not in fr_cache.details)
            log(f"FIFA Rosters: {len(specials)} spesialkort, hentet {n} nye kortsider, {missing} gjenstår")
            gcfg = sc.get("futgg") or {}
            if gcfg.get("enabled", True):
                # The special cards' own PlayStyles (FIFA Rosters has none; promo cards often have one more)
                fg = futgg.FutggCache(str(Path(cache_dir) / "futgg"))
                gfetch = PoliteFetcher(user_agent=gcfg.get("user_agent") or sc.get("user_agent") or "fc27-rating",
                                       delay_seconds=float(gcfg.get("delay_seconds", 3.0)), log=log)
                todo = [(str(e.get("player_id") or ""), fid) for fid, e in
                        sorted(unique_entries(fr_cache), key=lambda t: -t[1]["ovr"]) if not fr.is_base_version(e["version"])]
                try:
                    ng = futgg.fetch_cards(gfetch, fg, todo, int(gcfg.get("limit_per_run", 150)), log=log)
                    left = sum(1 for _, c in todo if c not in fg.cards)
                    log(f"FUT.GG: leste PlayStyles for {ng} spesialkort, {left} gjenstår")
                except Blocked as exc:
                    log(f"FUT.GG stoppet: {exc}")
                except Exception as exc:  # FUT.GG down or changed: the rest of the run goes on
                    log(f"FUT.GG feilet: {exc}")
                finally:
                    fg.save()
            if height_known is not None:
                # EA's FC 27 pages have no height. Base cards whose EA card lacks it (often new players)
                # get the FIFA Rosters card page, which has height and the real attributes. Best cards first.
                need = [fid for fid, e in unique_entries(fr_cache) if fr.is_base_version(e["version"])
                        and str(e.get("player_id")) not in height_known and fid not in fr_cache.details]
                need.sort(key=lambda fid: fr_cache.entries[fid]["ovr"], reverse=True)
                hl = int(frc.get("height_limit_per_run", 150))
                n2 = fr.fetch_details(fetcher, fr_cache, need, hl, log)
                log(f"FIFA Rosters: hentet {n2} kortsider for basekort uten høyde, {max(0, len(need) - n2)} gjenstår")
        except Blocked as exc:
            log(f"FIFA Rosters stoppet: {exc}")
        finally:
            fr_cache.save()

    if leaks:
        try:
            log("RealSport101: ser etter nye lekkasjer ...")
            rs.fetch_leaks(fetcher, leak_cache, sc["realsport101"]["category_url"],
                           sc["realsport101"].get("pages", 1), log=log)
        except Blocked as exc:
            log(f"RealSport101 stoppet: {exc}")
    return fr_cache, leak_cache
