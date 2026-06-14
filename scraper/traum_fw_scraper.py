"""
Scraper für traum-ferienwohnungen.de — Region: Schlei (SH)

Ausführen:
    cd fewo-ostsee
    python -m scraper.traum_fw_scraper

Voraussetzungen:
    pip install playwright beautifulsoup4 httpx
    playwright install chromium
"""
import asyncio
import logging
import re
import sys
import os
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, BrowserContext

# Pfad-Fix damit der Import aus dem Projektstamm funktioniert
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.anti_block import (
    get_browser_context_args,
    polite_delay,
    short_delay,
    simulate_human_scroll,
    MAX_LISTINGS_PER_RUN,
    MAX_PAGES_PER_RUN,
    REQUEST_TIMEOUT_MS,
)
from backend.database import SessionLocal, init_db
from backend.models import Listing, Preis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Konfiguration ──────────────────────────────────────────────────────────────

BASE_URL   = "https://www.traum-ferienwohnungen.de"

# Such-URL für die Schleiregion — ggf. anpassen falls Weiterleitung erfolgt
SEARCH_URL = (
    "https://www.traum-ferienwohnungen.de"
    "/urlaub/schleswig-holstein/schlei/?sort=relevance"
)

SOURCE_NAME = "traum-ferienwohnungen"


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _extract_int(text: Optional[str]) -> Optional[int]:
    """Extrahiert erste Ganzzahl aus einem String."""
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _extract_price(text: Optional[str]) -> Optional[float]:
    """Extrahiert Preis in EUR aus einem String wie '89 €/Nacht'."""
    if not text:
        return None
    # Entfernt Punkte als Tausendertrennzeichen, ersetzt Komma durch Punkt
    cleaned = re.sub(r"\.", "", text).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    return float(m.group(1)) if m else None


async def _get_page_html(page: Page, url: str) -> Optional[str]:
    """Lädt eine URL, wartet auf vollständiges Laden, gibt HTML zurück."""
    try:
        await page.goto(url, wait_until="domcontentloaded",
                        timeout=REQUEST_TIMEOUT_MS)
        await short_delay(1.0, 2.5)
        return await page.content()
    except Exception as e:
        log.warning(f"Fehler beim Laden von {url}: {e}")
        return None


# ── Listing-URL-Extraktion aus Suchergebnis-Seite ─────────────────────────────

def _parse_listing_urls(html: str) -> list[str]:
    """
    Extrahiert Listing-URLs aus einer Suchergebnisseite.
    Traum-FW nutzt Links der Form /p/<id>/ oder /ferienwohnung-<name>-<id>/
    """
    soup = BeautifulSoup(html, "html.parser")
    urls = []

    # Primärer Selektor: Karten mit data-object-id oder Links zu /p/
    for a in soup.select("a[href]"):
        href = a["href"]
        # Listing-URLs enthalten /p/<zahl>/ oder ähnliche Muster
        if re.search(r"/p/\d+", href) or re.search(r"/ferienwohnung.*-\d+/", href):
            full = urljoin(BASE_URL, href)
            if full not in urls:
                urls.append(full)

    log.info(f"  → {len(urls)} Listing-URLs auf dieser Seite gefunden")
    return urls


def _parse_next_page_url(html: str, current_url: str) -> Optional[str]:
    """Findet den Link zur nächsten Suchergebnisseite."""
    soup = BeautifulSoup(html, "html.parser")

    # Versuche typische Paginierungsmuster
    for a in soup.select("a[rel='next'], a.pagination__next, a[aria-label='Nächste Seite']"):
        href = a.get("href")
        if href:
            return urljoin(BASE_URL, href)

    # Fallback: Link mit ?page= oder &page= Parameter
    for a in soup.select("a[href*='page=']"):
        href = a.get("href", "")
        # Nur wenn es eine höhere Seitenzahl ist
        m_curr = re.search(r"page=(\d+)", current_url)
        m_next = re.search(r"page=(\d+)", href)
        curr_page = int(m_curr.group(1)) if m_curr else 1
        if m_next and int(m_next.group(1)) > curr_page:
            return urljoin(BASE_URL, href)

    return None


# ── Detail-Seite parsen ────────────────────────────────────────────────────────

def _parse_listing_detail(html: str, url: str) -> Optional[dict]:
    """
    Extrahiert alle relevanten Felder aus einer Listing-Detailseite.
    Selektoren müssen ggf. nach erstem Test angepasst werden.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Name ──────────────────────────────────────────────────────────────────
    name_el = (
        soup.select_one("h1.headline__title")
        or soup.select_one("h1[class*='title']")
        or soup.select_one("h1")
    )
    name = name_el.get_text(strip=True) if name_el else None
    if not name:
        log.warning(f"Kein Name gefunden für {url}")
        return None

    # ── Ort ───────────────────────────────────────────────────────────────────
    ort_el = (
        soup.select_one("[class*='location']")
        or soup.select_one("[class*='address']")
        or soup.select_one("[itemprop='addressLocality']")
    )
    ort = ort_el.get_text(strip=True) if ort_el else "Unbekannt"

    # ── Personen ──────────────────────────────────────────────────────────────
    personen_text = None
    for el in soup.select("[class*='person'], [class*='guest'], [class*='belegu']"):
        t = el.get_text(strip=True)
        if re.search(r"\d", t):
            personen_text = t
            break
    personen_max = _extract_int(personen_text)

    # ── Zimmer ────────────────────────────────────────────────────────────────
    zimmer_text = None
    for el in soup.select("[class*='room'], [class*='zimmer']"):
        t = el.get_text(strip=True)
        if re.search(r"\d", t):
            zimmer_text = t
            break
    zimmer = _extract_int(zimmer_text)

    # ── Preis ─────────────────────────────────────────────────────────────────
    preis_nacht = None
    for el in soup.select("[class*='price'], [class*='preis']"):
        t = el.get_text(strip=True)
        if "€" in t or "EUR" in t:
            preis_nacht = _extract_price(t)
            if preis_nacht:
                break

    # ── Ausstattung ───────────────────────────────────────────────────────────
    ausstattung_tags = []
    for el in soup.select("[class*='feature'], [class*='amenity'], [class*='ausstattung'] li"):
        tag = el.get_text(strip=True)
        if tag and len(tag) < 60:
            ausstattung_tags.append(tag)
    ausstattung = ", ".join(ausstattung_tags[:20]) if ausstattung_tags else None

    # ── Haustiere ─────────────────────────────────────────────────────────────
    haustiere = None
    page_text = soup.get_text().lower()
    if "hund" in page_text or "haustier" in page_text or "tier" in page_text:
        haustiere = "ja"

    # ── Geo (falls als JSON-LD oder data-Attribut vorhanden) ──────────────────
    latitude = longitude = None
    geo_el = soup.select_one("[data-lat]")
    if geo_el:
        try:
            latitude  = float(geo_el["data-lat"])
            longitude = float(geo_el["data-lng"])
        except (KeyError, ValueError):
            pass
    if not latitude:
        # JSON-LD Fallback
        import json
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "")
                if "geo" in data:
                    latitude  = float(data["geo"].get("latitude", 0)) or None
                    longitude = float(data["geo"].get("longitude", 0)) or None
            except Exception:
                pass

    # ── Source-ID aus URL ─────────────────────────────────────────────────────
    m = re.search(r"/p/(\d+)", url) or re.search(r"-(\d+)/?$", url)
    source_id = m.group(1) if m else url.split("/")[-2]

    return {
        "source_id":      source_id,
        "source":         SOURCE_NAME,
        "url":            url,
        "name":           name,
        "ort":            ort,
        "region":         "Schlei",
        "latitude":       latitude,
        "longitude":      longitude,
        "personen_max":   personen_max,
        "zimmer":         zimmer,
        "ausstattung":    ausstattung,
        "haustiere":      haustiere,
        "preis_nacht":    preis_nacht,   # wird separat gespeichert
    }


# ── Datenbankoperationen ───────────────────────────────────────────────────────

def _save_listing(db, data: dict) -> tuple[Listing, bool]:
    """
    Speichert oder aktualisiert ein Listing.
    Gibt (listing, neu_angelegt) zurück.
    """
    preis_nacht = data.pop("preis_nacht", None)

    existing = db.query(Listing).filter(
        Listing.source_id == data["source_id"]
    ).first()

    if existing:
        # Vorhandene Felder aktualisieren
        for k, v in data.items():
            if v is not None:
                setattr(existing, k, v)
        listing = existing
        neu = False
    else:
        listing = Listing(**data)
        db.add(listing)
        neu = True

    db.flush()   # ID generieren ohne commit

    # Preis als Snapshot speichern (immer, auch bei Updates)
    if preis_nacht:
        db.add(Preis(listing_id=listing.id, preis_pro_nacht=preis_nacht))

    db.commit()
    db.refresh(listing)
    return listing, neu


# ── Haupt-Scraper-Logik ───────────────────────────────────────────────────────

async def run_scraper():
    log.info("=" * 60)
    log.info("FeWo-Scraper startet — Schleiregion")
    log.info(f"Limit: {MAX_LISTINGS_PER_RUN} Listings, {MAX_PAGES_PER_RUN} Suchseiten")
    log.info("=" * 60)

    init_db()
    db = SessionLocal()

    ctx_args = get_browser_context_args()
    total_new = total_updated = total_errors = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,    # auf False setzen zum Debuggen
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context: BrowserContext = await browser.new_context(**ctx_args)

        # Automatisierungs-Fingerprint verstecken
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page: Page = await context.new_page()

        # ── Suchergebnisseiten durchgehen ─────────────────────────────────────
        current_search_url = SEARCH_URL
        listing_urls: list[str] = []

        for page_num in range(1, MAX_PAGES_PER_RUN + 1):
            log.info(f"Suchseite {page_num}: {current_search_url}")
            html = await _get_page_html(page, current_search_url)
            if not html:
                break

            await simulate_human_scroll(page)
            new_urls = _parse_listing_urls(html)
            listing_urls.extend(new_urls)

            if len(listing_urls) >= MAX_LISTINGS_PER_RUN:
                listing_urls = listing_urls[:MAX_LISTINGS_PER_RUN]
                log.info(f"Limit von {MAX_LISTINGS_PER_RUN} Listings erreicht.")
                break

            next_url = _parse_next_page_url(html, current_search_url)
            if not next_url:
                log.info("Keine weitere Suchseite gefunden — fertig.")
                break

            current_search_url = next_url
            await polite_delay(4.0, 9.0)  # zwischen Suchseiten: etwas länger warten

        log.info(f"\n{len(listing_urls)} Listing-URLs gesammelt. Starte Detail-Scraping...\n")

        # ── Detail-Seiten scrapen ──────────────────────────────────────────────
        for i, url in enumerate(listing_urls, 1):
            log.info(f"[{i}/{len(listing_urls)}] {url}")

            html = await _get_page_html(page, url)
            if not html:
                total_errors += 1
                continue

            await simulate_human_scroll(page)
            data = _parse_listing_detail(html, url)

            if not data:
                log.warning(f"  → Parsen fehlgeschlagen: {url}")
                total_errors += 1
            else:
                listing, neu = _save_listing(db, data)
                status = "NEU" if neu else "UPDATE"
                log.info(
                    f"  → [{status}] {listing.name!r} | "
                    f"{listing.ort} | {listing.personen_max} Pers."
                )
                if neu:
                    total_new += 1
                else:
                    total_updated += 1

            # Pause zwischen Detail-Seiten
            if i < len(listing_urls):
                await polite_delay(3.0, 7.0)

        await browser.close()

    db.close()

    log.info("\n" + "=" * 60)
    log.info(f"Scraping abgeschlossen: {datetime.now():%H:%M:%S}")
    log.info(f"  Neu:        {total_new}")
    log.info(f"  Aktualisiert: {total_updated}")
    log.info(f"  Fehler:     {total_errors}")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_scraper())
