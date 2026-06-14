"""
Firecrawl-basierter Scraper für traum-ferienwohnungen.de — Schlei-Region.

Voraussetzungen:
    pip install firecrawl-py
    FIRECRAWL_API_KEY als Umgebungsvariable setzen (oder in .env)

Ausführen:
    python -m scraper.firecrawl_scraper
"""
import logging
import os
import re
import sys

from firecrawl import FirecrawlApp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal, init_db
from backend.models import Listing, Preis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SEARCH_URL = "https://www.traum-ferienwohnungen.de/europa/deutschland/schlei/"
BASE_URL    = "https://www.traum-ferienwohnungen.de"
SOURCE_NAME = "traum-ferienwohnungen"
MAX_LISTINGS = 80


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _extract_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", str(text))
    return int(m.group()) if m else None


def _extract_price(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"\.", "", str(text)).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    return float(m.group(1)) if m else None


def _extract_source_id(url: str) -> str:
    m = re.search(r"/p/(\d+)", url) or re.search(r"-(\d+)/?$", url)
    return m.group(1) if m else url.split("/")[-2]


# ── Listing-URLs aus Suchergebnis-Markdown ─────────────────────────────────────

def _parse_listing_urls_from_links(links: list[str]) -> list[str]:
    """Filtert echte Listing-URLs aus der Link-Liste von Firecrawl."""
    urls = []
    for url in links:
        # Format: traum-ferienwohnungen.de/12345/ oder /ferienhaus/12345/
        if re.search(r"traum-ferienwohnungen\.de/(?:ferienhaus/|ferienwohnung/)?(\d{4,})/?$", url):
            if url not in urls:
                urls.append(url)
    log.info(f"  → {len(urls)} Listing-URLs gefunden")
    return urls


# ── Detail-Seite parsen ────────────────────────────────────────────────────────

def _parse_listing_from_markdown(markdown: str, url: str, metadata: dict) -> dict | None:
    """Extrahiert Listing-Daten aus dem Firecrawl-Markdown einer Detailseite."""

    # Name aus Metadata oder erstem H1
    # metadata ist ein Pydantic-Objekt — Attribut-Zugriff statt .get()
    name = getattr(metadata, "title", None) or getattr(metadata, "og_title", None)
    if not name:
        m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        name = m.group(1).strip() if m else None
    if not name:
        log.warning(f"Kein Name gefunden für {url}")
        return None

    # Ort
    ort = getattr(metadata, "og_locale", None) or "Unbekannt"
    for pattern in [r"(?:Lage|Ort|Adresse)[:\s]+([A-ZÄÖÜ][^\n,]+)", r"in\s+([A-ZÄÖÜ][a-zäöü]+(?:\s[A-ZÄÖÜ]?[a-zäöü]+)?)"]:
        m = re.search(pattern, markdown)
        if m:
            ort = m.group(1).strip()
            break

    # Personen
    personen_max = None
    for pattern in [r"(\d+)\s*(?:Personen|Person|Gäste|Schlafplätze)", r"bis\s+zu\s+(\d+)\s*(?:Personen|Gäste)"]:
        m = re.search(pattern, markdown, re.IGNORECASE)
        if m:
            personen_max = int(m.group(1))
            break

    # Zimmer
    zimmer = None
    m = re.search(r"(\d+)\s*(?:Zimmer|Schlafzimmer|Räume)", markdown, re.IGNORECASE)
    if m:
        zimmer = int(m.group(1))

    # Preis
    preis_nacht = None
    for pattern in [r"(\d+(?:[.,]\d+)?)\s*€\s*/?\s*Nacht", r"ab\s*(\d+(?:[.,]\d+)?)\s*€"]:
        m = re.search(pattern, markdown, re.IGNORECASE)
        if m:
            preis_nacht = _extract_price(m.group(1))
            break

    # Haustiere
    haustiere = None
    if re.search(r"haustier|hund|tier", markdown, re.IGNORECASE):
        haustiere = "ja"

    # Geo aus Metadata
    latitude = longitude = None
    geo = getattr(metadata, "geo", None)
    if geo:
        try:
            latitude  = float(getattr(geo, "latitude", 0) or 0) or None
            longitude = float(getattr(geo, "longitude", 0) or 0) or None
        except (TypeError, ValueError):
            pass

    return {
        "source_id":    _extract_source_id(url),
        "source":       SOURCE_NAME,
        "url":          url,
        "name":         name.strip(),
        "ort":          ort.strip(),
        "region":       "Schlei",
        "latitude":     latitude,
        "longitude":    longitude,
        "personen_max": personen_max,
        "zimmer":       zimmer,
        "haustiere":    haustiere,
        "preis_nacht":  preis_nacht,
    }


# ── Datenbankoperationen ───────────────────────────────────────────────────────

def _save_listing(db, data: dict) -> tuple[Listing, bool]:
    preis_nacht = data.pop("preis_nacht", None)
    existing = db.query(Listing).filter(Listing.source_id == data["source_id"]).first()
    if existing:
        for k, v in data.items():
            if v is not None:
                setattr(existing, k, v)
        listing = existing
        neu = False
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


# ── Haupt-Logik ────────────────────────────────────────────────────────────────

def run_scraper():
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        log.error("FIRECRAWL_API_KEY nicht gesetzt! Bitte als Umgebungsvariable setzen.")
        log.error("  Windows: $env:FIRECRAWL_API_KEY = 'fc-...'")
        sys.exit(1)

    app = FirecrawlApp(api_key=api_key)
    init_db()
    db = SessionLocal()

    log.info("=" * 60)
    log.info("Firecrawl-Scraper startet — Schleiregion")
    log.info("=" * 60)

    # ── Schritt 1: Suchergebnisseite scrapen ──────────────────────────────────
    log.info(f"Scrape Suchseite: {SEARCH_URL}")
    result = app.scrape_url(SEARCH_URL, formats=["links"])
    listing_urls = _parse_listing_urls_from_links(result.links or [])

    listing_urls = listing_urls[:MAX_LISTINGS]
    log.info(f"{len(listing_urls)} Listings werden verarbeitet.")

    # ── Schritt 2: Detail-Seiten ───────────────────────────────────────────────
    total_new = total_updated = total_errors = 0

    for i, url in enumerate(listing_urls, 1):
        log.info(f"[{i}/{len(listing_urls)}] {url}")
        try:
            detail = app.scrape_url(url, formats=["markdown"])
            data = _parse_listing_from_markdown(
                detail.markdown or "",
                url,
                detail.metadata or {},
            )
            if not data:
                log.warning(f"  → Parsen fehlgeschlagen")
                total_errors += 1
                continue

            listing, neu = _save_listing(db, data)
            status = "NEU" if neu else "UPDATE"
            log.info(f"  → [{status}] {listing.name!r} | {listing.ort} | {listing.personen_max} Pers.")
            if neu:
                total_new += 1
            else:
                total_updated += 1

        except Exception as e:
            log.error(f"  → Fehler: {e}")
            total_errors += 1

    db.close()
    log.info("=" * 60)
    log.info(f"Fertig — Neu: {total_new} | Update: {total_updated} | Fehler: {total_errors}")
    log.info("=" * 60)


if __name__ == "__main__":
    run_scraper()
