"""Files that make the pages work as a small private website.

write_assets() puts fonts, icons, the web app manifest and om.html (sources,
disclaimer and privacy) next to rapport.html and evolab.html, so the pages work
the same opened from disk as on the web, without fetching anything from others.

publish() builds the folder that is uploaded (site/ by default): the two pages,
index.html, the assets, robots.txt and a _headers file for Cloudflare Pages.
Data files (ratings.csv/json, evolab.csv) are left out on purpose.
"""
from __future__ import annotations

import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
_DIR = Path(__file__).resolve().parent
ASSETS = _DIR / "site_assets"
ABOUT = _DIR / "about_page.html"
MARKER = ".fcrating-site"
MAX_FILE_BYTES = 25 * 1024 * 1024  # Cloudflare Pages: 25 MiB per file
SPLIT_BYTES = 20 * 1024 * 1024     # bigger pages get their card data moved into separate files
CHUNK_BYTES = 8 * 1024 * 1024
PAGES = ("rapport.html", "evolab.html")

HEADERS = """/*
  X-Robots-Tag: noindex, nofollow
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'

/fonts/*
  Cache-Control: public, max-age=31536000, immutable
"""

ROBOTS = "User-agent: *\nDisallow: /\n"

ACCESS_ITEMS = (
    '<li>Innlogging: siden er låst med Cloudflare Access. Du logger inn med e-postadressen din og en '
    'engangskode som sendes dit. Bare adresser som eieren har lagt inn, slipper inn.</li>\n'
    '<li>Cloudflare leverer siden. For å sjekke tilgangen, levere sidene og stoppe misbruk behandler Cloudflare '
    'e-postadressen og IP-adressen din, og lagrer en nødvendig innloggingskapsel (CF_Authorization) i nettleseren '
    'din, så du slipper å logge inn hver gang. Den brukes ikke til noe annet. Se '
    '<a href="https://www.cloudflare.com/privacypolicy/" rel="noopener" target="_blank">Cloudflares personvernerklæring</a>.</li>\n'
    '<li>Vil du ikke lenger ha tilgang, si fra til eieren, så fjernes e-postadressen din fra listen.</li>'
)
PASSWORD_ITEM = ("<li>Innlogging: siden er låst med et felles passord. Nettleseren husker det til du lukker den. "
                 "Cloudflare leverer siden og behandler IP-adressen din for å levere den og stoppe misbruk.</li>")
OPEN_ITEM = ("<li>Siden er åpen for alle som har lenken, men den deles bare med venner og er stengt for "
             "søkemotorer. Ingen innlogging, så ingenting om deg registreres av siden. GitHub Pages leverer siden "
             "og lagrer IP-adressen til besøkende av sikkerhetshensyn. Se "
             '<a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement" '
             'rel="noopener" target="_blank">GitHubs personvernerklæring</a>.</li>')
LOCAL_ITEM = "<li>Denne kopien ligger bare på eierens egen maskin.</li>"
OPEN_VALUES = ("åpen", "apen", "github-pages", "offentlig")


def user_config_path() -> Path:
    """Your own settings. Lives in data/, so a new version of the program never overwrites it."""
    return ROOT / "data" / "side.json"


def site_config(path: Optional[Path] = None) -> dict:
    """Defaults from config/site.json, then your settings from data/side.json (or path)."""
    cfg = {"eier": "", "kontakt": "", "innlogging": "", "cloudflare_prosjekt": "fc27-rating"}
    for p in ([Path(path)] if path else [ROOT / "config" / "site.json", user_config_path()]):
        if p.exists():
            with open(p, encoding="utf-8") as f:
                cfg.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in cfg.items()}


def ensure_user_config() -> Optional[Path]:
    """Create data/side.json from config/site.json the first time. Returns the path if it was made."""
    p = user_config_path()
    if p.exists():
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config" / "site.json", p)
    return p


def _contact_html(contact: str) -> str:
    c = html.escape(contact)
    if "@" in contact and " " not in contact and not contact.startswith(("http://", "https://")):
        return f'<a href="mailto:{c}">{c}</a>'
    if contact.startswith(("http://", "https://")):
        return f'<a href="{c}" rel="noopener" target="_blank">{c}</a>'
    return c


def render_about(cfg: Optional[dict] = None, stamp: Optional[str] = None) -> str:
    from .report import PAGE_CSS
    cfg = cfg if cfg is not None else site_config()
    owner, contact, login = cfg.get("eier", ""), cfg.get("kontakt", ""), cfg.get("innlogging", "")
    contact_line = f"Kontakt: {_contact_html(contact)}." if contact else "Si fra til eieren av siden."
    access = "Bare de som har fått tilgang, kan åpne den."
    if login == "cloudflare-access":
        login_items = ACCESS_ITEMS
    elif login == "passord":
        login_items = PASSWORD_ITEM
    elif login.lower() in OPEN_VALUES:
        login_items = OPEN_ITEM
        access = "Lenken deles bare med venner, og siden er ikke med i søkemotorer."
    elif login:
        login_items = f"<li>Innlogging: {html.escape(login)}</li>"
    else:
        login_items = LOCAL_ITEM
        access = "Denne kopien ligger bare på eierens maskin."
    if owner and contact:
        owner_line = f"Ansvarlig for siden er {html.escape(owner)} ({_contact_html(contact)})."
    elif owner:
        owner_line = f"Ansvarlig for siden er {html.escape(owner)}."
    elif contact:
        owner_line = f"Spørsmål om personvern: {_contact_html(contact)}."
    else:
        owner_line = "Spørsmål om personvern går til eieren av siden."
    stamp = stamp or datetime.now().strftime("%d.%m.%Y")
    page = ABOUT.read_text(encoding="utf-8")
    return (page.replace("__CSS__", PAGE_CSS).replace("__CONTACT_LINE__", contact_line)
            .replace("__LOGIN_ITEMS__", login_items).replace("__OWNER_LINE__", owner_line)
            .replace("__ACCESS_SENTENCE__", access)
            .replace("__STAMP__", html.escape(stamp)))


def write_assets(out_dir, cfg: Optional[dict] = None) -> Path:
    """Fonts, icons, manifest and om.html next to the pages. Returns the om.html path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for item in ASSETS.iterdir():
        if item.is_dir():
            shutil.copytree(item, out / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, out / item.name)
    about = out / "om.html"
    about.write_text(render_about(cfg), encoding="utf-8")
    return about


def split_data(page: Path, limit: Optional[int] = None, chunk: Optional[int] = None) -> List[str]:
    """Move the card list (const RAW=[...]) of a page bigger than limit into script files of about
    chunk bytes each, loaded before the page script. Returns the new file names (none if it fits)."""
    limit = SPLIT_BYTES if limit is None else limit
    chunk = CHUNK_BYTES if chunk is None else chunk
    text = page.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) <= limit:
        return []
    start = text.index("const RAW=") + len("const RAW=")
    rows, end = json.JSONDecoder().raw_decode(text, start)
    var = "__RAW_" + "".join(c for c in page.stem.upper() if c.isalnum())
    parts: List[List[str]] = [[]]
    size = 0
    for row in rows:
        item = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        if parts[-1] and size + len(item.encode("utf-8")) > chunk:
            parts.append([])
            size = 0
        parts[-1].append(item)
        size += len(item.encode("utf-8")) + 1
    names = []
    for i, part in enumerate(parts, 1):
        name = f"{page.stem}-data-{i}.js"
        (page.parent / name).write_text(f"window.{var}=(window.{var}||[]).concat([{','.join(part)}]);\n",
                                        encoding="utf-8")
        names.append(name)
    tags = "".join(f'<script src="{n}"></script>' for n in names)
    text = text[:start] + f"window.{var}||[]" + text[end:]
    # right before the script that reads RAW (not just the last script: small scripts may follow it)
    at = text.rindex("<script>", 0, text.index(f"window.{var}||[]"))
    page.write_text(text[:at] + tags + "\n" + text[at:], encoding="utf-8")
    return names


def _clear(dest: Path) -> None:
    """Empty the site folder, but only if it is one this program made (or empty)."""
    if not dest.exists():
        return
    if not dest.is_dir():
        raise SystemExit(f"{dest} finnes og er ikke en mappe.")
    if any(dest.iterdir()) and not (dest / MARKER).exists():
        raise SystemExit(f"{dest} er ikke tom og ble ikke laget av publiser. Velg en annen mappe med --til.")
    shutil.rmtree(dest)


def publish(out_dir=None, site_dir=None, cfg: Optional[dict] = None) -> Dict[str, object]:
    """Build the upload folder from output/. Returns {"dir", "files", "warnings"}."""
    src = Path(out_dir) if out_dir else ROOT / "output"
    dest = Path(site_dir) if site_dir else ROOT / "site"
    cfg = cfg if cfg is not None else site_config()
    if not (src / "rapport.html").exists():
        raise SystemExit(f"Fant ikke {src / 'rapport.html'}. Kjør rate først.")
    _clear(dest)
    dest.mkdir(parents=True)
    (dest / MARKER).write_text("Laget av: py -m fcrating publiser. Mappen tømmes hver gang.\n", encoding="utf-8")
    warnings: List[str] = []
    for name in PAGES:
        if (src / name).exists():
            shutil.copy2(src / name, dest / name)
            split_data(dest / name)
        elif name == "evolab.html":
            warnings.append("evolab.html mangler (kjørte du rate med --uten-evolab?). Lenken til Evo Lab vil ikke virke.")
    shutil.copy2(dest / "rapport.html", dest / "index.html")
    write_assets(dest, cfg)
    (dest / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    (dest / "_headers").write_text(HEADERS, encoding="utf-8")
    files = sorted(p for p in dest.rglob("*") if p.is_file() and p.name != MARKER)
    for p in files:
        if p.stat().st_size > MAX_FILE_BYTES:
            warnings.append(f"{p.name} er {p.stat().st_size / 1048576:.1f} MiB. Cloudflare Pages tar maks 25 MiB per fil.")
    if not cfg.get("kontakt"):
        warnings.append("Kontakt er tom i data/side.json. Fyll den inn før du deler siden (brukes på om.html).")
    if not cfg.get("eier"):
        warnings.append("Eier er tom i data/side.json.")
    if not cfg.get("innlogging"):
        warnings.append("Innlogging er tom i data/side.json. Skriv åpen (GitHub Pages), cloudflare-access eller passord der (se README).")
    return {"dir": str(dest), "files": [str(p.relative_to(dest)) for p in files], "warnings": warnings}
