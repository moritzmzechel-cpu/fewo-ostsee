"""
Schlei-Scraper für traum-ferienwohnungen.de — direkter HTTP-Zugriff.

Erkenntnis aus der Analyse: Sowohl Region- als auch Detailseiten sind per
plain httpx erreichbar (kein Bot-Schutz, kein Firecrawl nötig). Die
Detailseiten liefern strukturierte JSON-LD-Daten (schema.org/VacationRental)
inklusive exakter Geo-Koordinaten und vollständiger Adresse.

Fokus: Region Schlei inkl. Olpenitz (in Hauptliste) und Schönhagen.

Ausführen:
    python -m scraper.schlei_scraper
"""
import asyncio
import json
import logging
import os
import random
import re
import sys
import time

import httpx
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, init_db
from backend.models import Listing, Preis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL    = "https://www.traum-ferienwohnungen.de"
SOURCE_NAME = "traum-ferienwohnungen"

# Region-Übersichtsseiten, von denen wir Listing-IDs sammeln.
# Olpenitz hat keinen eigenen Pfad — die Objekte stehen in der Schlei-Hauptliste.
REGION_URLS = [
    f"{BASE_URL}/europa/deutschland/schlei/",
    f"{BASE_URL}/europa/deutschland/schlei/schoenhagen/",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]


def _headers(ua: str | None = None) -> dict:
    return {
        "User-Agent": ua or random.choice(USER_AGENTS),
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }


# ── HTTP-Helfer ────────────────────────────────────────────────────────────────

def _polite_sleep(lo: float = 1.5, hi: float = 3.5) -> None:
    time.sleep(random.uniform(lo, hi))


def _fetch(url: str) -> str | None:
    """Frische Verbindung pro Request — vermeidet keep-alive Rate-Limiting."""
    try:
        with httpx.Client(headers=_headers(), timeout=30) as client:
            r = client.get(url, follow_redirects=True)
        if r.status_code != 200:
            log.warning(f"  HTTP {r.status_code} bei {url}")
            return None
        return r.text
    except Exception as e:
        log.warning(f"  Fehler bei {url}: {e}")
        return None


# Firecrawl-Client wird lazy initialisiert (nur als Fallback bei IP-Rate-Limit)
_firecrawl_app = None
_firecrawl_disabled = False


def _fetch_firecrawl(url: str) -> str | None:
    """Fallback: Firecrawl scrapt über eigene IPs und umgeht IP-Rate-Limiting."""
    global _firecrawl_app, _firecrawl_disabled
    if _firecrawl_disabled:
        return None
    if _firecrawl_app is None:
        key = os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            log.info("  (Kein FIRECRAWL_API_KEY — Fallback deaktiviert)")
            _firecrawl_disabled = True
            return None
        try:
            from firecrawl import FirecrawlApp
            _firecrawl_app = FirecrawlApp(api_key=key)
        except Exception as e:
            log.warning(f"  Firecrawl-Init fehlgeschlagen: {e}")
            _firecrawl_disabled = True
            return None
    try:
        log.info(f"  ↪ Firecrawl-Fallback für {url}")
        res = _firecrawl_app.scrape_url(url, formats=["rawHtml"])
        return res.raw_html or None
    except Exception as e:
        log.warning(f"  Firecrawl-Fehler: {e}")
        return None


# ── Listing-IDs aus Region-Seite ───────────────────────────────────────────────

def _parse_listing_urls(html: str) -> list[str]:
    """Findet alle Detail-URLs (Format /12345/ oder /ferienhaus/12345/)."""
    urls = []
    for path, _id in re.findall(
        r'(/(?:ferienhaus/|ferienwohnung/)?(\d{4,}))/?(?:["\'?#]|\s)', html
    ):
        full = f"{BASE_URL}{path}/"
        if full not in urls:
            urls.append(full)
    return urls


# ── Detail-Seite via JSON-LD parsen ────────────────────────────────────────────

def _extract_jsonld(html: str) -> dict:
    """Sammelt relevante JSON-LD-Objekte (VacationRental/Product) zu einem Dict."""
    soup = BeautifulSoup(html, "html.parser")
    merged: dict = {}
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") in ("VacationRental", "Product", "LodgingBusiness", "Accommodation"):
                # Spätere, vollständigere Blöcke überschreiben frühere
                merged.update({k: v for k, v in item.items() if v})
    return merged


def _extract_coords(html: str) -> tuple[float | None, float | None]:
    """Erster lat/lng-Treffer = das Objekt selbst (spätere = Nachbar-Empfehlungen)."""
    lat = re.search(r'"lat(?:itude)?"\s*[:=]\s*"?(-?\d{2}\.\d+)', html)
    lng = re.search(r'"l(?:o)?ng(?:itude)?"\s*[:=]\s*"?(-?\d{1,2}\.\d+)', html)
    return (
        float(lat.group(1)) if lat else None,
        float(lng.group(1)) if lng else None,
    )


def _extract_price(jsonld: dict, html: str) -> float | None:
    offers = jsonld.get("offers")
    if isinstance(offers, dict):
        p = offers.get("price") or offers.get("lowPrice")
        if p:
            try:
                return float(str(p).replace(",", "."))
            except ValueError:
                pass
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*€\s*/?\s*Nacht', html)
    return float(m.group(1).replace(",", ".")) if m else None


def _title_fallback(html: str) -> tuple[str | None, str | None]:
    """Manche Listings liefern nur BreadcrumbList-JSON-LD (kein VacationRental-Block).
    <title> folgt aber konsistent dem Muster 'Name, Ort, Vermieter'."""
    m = re.search(r"<title>([^<|]+)", html)
    if not m:
        return None, None
    title = re.sub(r"\s*-\s*Traum-Ferienwohnungen.*$", "", m.group(1)).strip()
    parts = [p.strip() for p in title.split(",")]
    name = parts[0] if parts else title
    ort = parts[1] if len(parts) > 1 else None
    return name or None, ort


def _parse_detail(html: str, url: str) -> dict | None:
    jsonld = _extract_jsonld(html)
    name = jsonld.get("name")
    addr = jsonld.get("address") or {}
    if isinstance(addr, list):
        addr = addr[0] if addr else {}

    # Schema ist leicht invertiert: addressRegion = echter Ort, addressLocality = "Schlei"
    ort = addr.get("addressRegion") or addr.get("addressLocality")
    plz = addr.get("postalCode")
    strasse = addr.get("streetAddress")

    # Fallback: manche Listings liefern nur BreadcrumbList-JSON-LD, kein VacationRental
    if not name:
        name, fallback_ort = _title_fallback(html)
        ort = ort or fallback_ort
    if not name:
        log.warning(f"  Kein Name extrahierbar bei {url}")
        return None
    ort = ort or "Unbekannt"

    lat, lng = _extract_coords(html)

    # Personen aus JSON-LD oder Text
    personen = None
    occ = jsonld.get("occupancy") or {}
    if isinstance(occ, dict):
        personen = occ.get("value") or occ.get("maxValue")
    if not personen:
        m = re.search(r'(\d+)\s*(?:Personen|Gäste|Schlafplätze)', html, re.IGNORECASE)
        personen = int(m.group(1)) if m else None
    if personen:
        personen = int(personen)

    haustiere = "ja" if re.search(r'haustier|hund erlaubt', html, re.IGNORECASE) else None

    m_id = re.search(r"/(\d{4,})/?$", url)
    source_id = m_id.group(1) if m_id else url.rstrip("/").split("/")[-1]

    return {
        "source_id":    source_id,
        "source":       SOURCE_NAME,
        "url":          url,
        "name":         name.strip(),
        "ort":          str(ort).strip(),
        "region":       "Schlei",
        "strasse":      f"{strasse}, {plz}".strip(", ") if strasse else None,
        "latitude":     lat,
        "longitude":    lng,
        "personen_max": personen,
        "haustiere":    haustiere,
        "preis_nacht":  _extract_price(jsonld, html),
    }


# ── Speichern ──────────────────────────────────────────────────────────────────

def _save_listing(db, data: dict) -> tuple[Listing, bool]:
    preis_nacht = data.pop("preis_nacht", None)
    existing = db.query(Listing).filter(Listing.source_id == data["source_id"]).first()
    if existing:
        for k, v in data.items():
            if v is not None:
                setattr(existing, k, v)
        listing, neu = existing, False
    else:
        listing = Listing(**data)
        db.add(listing)
        neu = True
    db.flush()
    if preis_nacht:
        db.add(Preis(listing_id=listing.id, preis_pro_nacht=preis_nacht))
    db.commit()
    db.refresh(listing)
    return listing, neu


# ── Hauptlogik ─────────────────────────────────────────────────────────────────

def run_scraper():
    init_db()
    db = SessionLocal()

    log.info("=" * 60)
    log.info("Schlei-Scraper (httpx + JSON-LD) — Olpenitz / Schönhagen / Schlei")
    log.info("=" * 60)

    # Schritt 1: Listing-URLs aus allen Region-Seiten sammeln
    all_urls: list[str] = []
    for region_url in REGION_URLS:
        log.info(f"Region: {region_url}")
        html = _fetch(region_url)
        if not html:
            continue
        urls = _parse_listing_urls(html)
        log.info(f"  → {len(urls)} Listings gefunden")
        for u in urls:
            if u not in all_urls:
                all_urls.append(u)
        _polite_sleep()

    log.info(f"\nGesamt: {len(all_urls)} eindeutige Listings\n")

    # Schritt 2: Detailseiten scrapen. Cumulatives IP-Rate-Limiting kippt nach
    # ~15 schnellen Requests → gescheiterte URLs sammeln und nach Cooldown erneut.
    stats = {"new": 0, "upd": 0, "geo": 0}

    def _process(url: str, idx: int, total: int) -> bool:
        """Scrapt + speichert ein Listing. True bei Erfolg."""
        html = _fetch(url)
        data = _parse_detail(html, url) if html else None
        if not data:
            html = _fetch_firecrawl(url)  # Fallback über fremde IPs
            data = _parse_detail(html, url) if html else None
        if not data:
            return False
        has_geo = data["latitude"] is not None
        listing, neu = _save_listing(db, data)
        stats["geo"] += int(has_geo)
        stats["new"] += int(neu)
        stats["upd"] += int(not neu)
        geo_str = f"({listing.latitude:.4f}, {listing.longitude:.4f})" if has_geo else "(keine Geo)"
        log.info(f"[{idx}/{total}] {'NEU' if neu else 'UPD'} | "
                 f"{listing.name[:45]!r} | {listing.ort} {geo_str}")
        return True

    # Batch-Verarbeitung: die Seite hat ein gleitendes Rate-Limit. In Blöcken
    # arbeiten und zwischen den Blöcken pausieren hält uns dauerhaft darunter.
    BATCH_SIZE = 6
    COOLDOWN   = 45

    failed = []
    total = len(all_urls)
    for start in range(0, total, BATCH_SIZE):
        batch = all_urls[start:start + BATCH_SIZE]
        if start:
            log.info(f"  …{COOLDOWN}s Cooldown (Rate-Limit-Schutz)…")
            time.sleep(COOLDOWN)
        for k, url in enumerate(batch):
            i = start + k + 1
            if not _process(url, i, total):
                log.warning(f"[{i}/{total}] Block fehlgeschlagen: {url}")
                failed.append(url)
            _polite_sleep()

    # Abschluss-Durchgang für Nachzügler nach längerem Cooldown
    if failed:
        log.info(f"\n{len(failed)} Nachzügler — {COOLDOWN}s Cooldown, dann letzter Versuch...\n")
        time.sleep(COOLDOWN)
        still_failed = []
        for j, url in enumerate(failed, 1):
            if not _process(url, j, len(failed)):
                still_failed.append(url)
            _polite_sleep(4.0, 7.0)
        failed = still_failed

    db.close()
    total_err = len(failed)
    log.info("=" * 60)
    log.info(f"Fertig — Neu: {stats['new']} | Update: {stats['upd']} | "
             f"mit Geo: {stats['geo']}/{len(all_urls)} | Fehler: {total_err}")
    log.info("=" * 60)


if __name__ == "__main__":
    run_scraper()
