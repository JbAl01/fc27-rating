"""FIFA Rosters (fifarosters.com): released FC 27 cards incl. Icons, TOTW and promos.

The FC 27 FUT list shows every card with OVR, position, version, work rates,
skill moves, weak foot and face stats, and links each card to a page with all
detailed attributes and height. Card links carry EA's player id, so special
cards are matched to their EA base card exactly.

Fetching is polite: robots.txt is respected, there is a pause between
requests, and detail pages are cached so each card is only fetched once.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

from ..htmltext import extract
from .local import parse_page_text

BASE_URL = "https://www.fifarosters.com/"
POSITIONS = r"(GK|CB|LB|RB|LWB|RWB|CDM|CM|CAM|LM|RM|LW|RW|ST|CF)"

_HEAD = re.compile(
    r"^\s*(?P<ovr>\d{2})\s*(?P<name>.+?)\s*(?P<pos>" + POSITIONS[1:] +
    r"\s*League\s*(?P<league>\d+)\s*(?P<rest>.*?)\s*Work\s*(?P<wa>[HML])\s*/\s*(?P<wd>[HML])"
    r"\s*Skill\s*(?P<sm>\d)\s*Weak\s*(?P<wf>\d)\s*Foot\s*(?P<foot>[LR])", re.S)
_FACE = re.compile(r"(\d{1,2})\s*PAC\s*(\d{1,2})\s*SHO\s*(\d{1,2})\s*PAS\s*(\d{1,2})\s*DRI\s*"
                   r"(\d{1,2})\s*DEF\s*(\d{1,2})\s*PHY")
_GK_FACE = re.compile(r"(\d{1,2})\s*DIV\s*(\d{1,2})\s*HAN\s*(\d{1,2})\s*KIC\s*(\d{1,2})\s*REF\s*"
                      r"(\d{1,2})\s*SPD\s*(\d{1,2})\s*POS")
_BASE_VERSION = re.compile(r"(fc\s*\d+\s*)?((non[- ]?)?rare|common)?\s*(gold|silver|bronze)?", re.I)


def is_base_version(version: str) -> bool:
    v = (version or "").strip()
    return bool(v) and bool(_BASE_VERSION.fullmatch(v))


def parse_entry(text: str, href: str) -> Optional[dict]:
    """Parse one card link from a list page."""
    m = _HEAD.search(text)
    if not m:
        return None
    q = parse_qs(urlparse(href).query)
    name = m.group("name").strip()
    rest = re.sub(r"^\d+\s*", "", m.group("rest").strip())
    for candidate in (name, name.split()[-1]):
        if rest.lower().startswith(candidate.lower()):
            rest = rest[len(candidate):].strip()
            break
    face: Dict[str, float] = {}
    fm = _FACE.search(text)
    if fm:
        face = dict(zip(["pac", "sho", "pas", "dri", "def", "phy"], map(float, fm.groups())))
    else:
        gm = _GK_FACE.search(text)
        if gm:
            face = dict(zip(["div", "han", "kic", "ref", "spd", "pos"], map(float, gm.groups())))
    return {
        "ovr": int(m.group("ovr")),
        "name": name,
        "position": m.group("pos"),
        "version": rest or "Ukjent",
        "work_rates": f"{m.group('wa')}/{m.group('wd')}",
        "skill_moves": int(m.group("sm")),
        "weak_foot": int(m.group("wf")),
        "foot": "Left" if m.group("foot") == "L" else "Right",
        "face": face,
        "player_id": (q.get("player") or [None])[0],
        "futid": (q.get("futid") or [None])[0],
        "url": urljoin(BASE_URL, href),
    }


GAME_VERSION = "27"


def parse_list_page(html: str, version: Optional[str] = GAME_VERSION) -> List[dict]:
    """Cards on a list page. Links to other game versions (some promo pages on
    FIFA Rosters still show FIFA 17 cards) are skipped; version=None keeps all."""
    _, links, _ = extract(html)
    out, seen = [], set()
    for href, text in links:
        if "player=" not in href or "futid=" not in href:
            continue
        v = (parse_qs(urlparse(href).query).get("v") or [None])[0]
        if version is not None and v is not None and v != version:
            continue
        entry = parse_entry(text, href)
        if entry and entry["futid"] not in seen:
            seen.add(entry["futid"])
            out.append(entry)
    return out


def parse_detail_page(html: str) -> dict:
    text, _, _ = extract(html)
    info = parse_page_text(text)
    return {
        "attributes": info["attributes"],
        "height_cm": info.get("height_cm"),
        "skill_moves": info.get("skill_moves"),
        "weak_foot": info.get("weak_foot"),
        "work_rates": info.get("work_rates"),
    }


class FifaRostersCache:
    """Keeps every card seen in list pages (by futid) and parsed detail pages."""

    def __init__(self, folder: str):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.entries_file = self.folder / "kort.json"
        self.details_file = self.folder / "detaljer.json"
        self.meta_file = self.folder / "meta.json"
        self.entries: Dict[str, dict] = self._load(self.entries_file)
        self.details: Dict[str, dict] = self._load(self.details_file)
        self.meta: dict = self._load(self.meta_file)

    @staticmethod
    def _load(path: Path):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self) -> None:
        for path, data in ((self.entries_file, self.entries), (self.details_file, self.details),
                           (self.meta_file, self.meta)):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)


def scan_list(fetcher, cache: FifaRostersCache, url_template: str, max_pages: Optional[int],
              log=print) -> int:
    """Walk a paginated list until a page has no new cards. Returns cards found."""
    found, page, previous = 0, 1, None
    while True:
        html = fetcher.get(url_template.format(page=page))
        entries = parse_list_page(html)
        ids = [e["futid"] for e in entries]
        if not entries or ids == previous:
            break
        for e in entries:
            cache.entries[e["futid"]] = e
        found += len(entries)
        if page % 25 == 0:
            log(f"  FIFA Rosters: side {page}, {found} kort")
            cache.save()
        previous = ids
        page += 1
        if max_pages and page > max_pages:
            break
    cache.save()
    return found


def fetch_details(fetcher, cache: FifaRostersCache, futids: List[str], limit: int, log=print) -> int:
    done = 0
    for futid in futids:
        if done >= limit:
            break
        entry = cache.entries.get(futid)
        if not entry or futid in cache.details:
            continue
        cache.details[futid] = parse_detail_page(fetcher.get(entry["url"]))
        done += 1
        if done % 25 == 0:
            log(f"  FIFA Rosters: {done} kortsider hentet")
            cache.save()
    cache.save()
    return done
