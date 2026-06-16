"""
Olpenitz-Scraper — nutzt die echte Such-API von traum-ferienwohnungen.de.

Hintergrund: Die SEO-Landingpages (z.B. /europa/deutschland/schlei/) zeigen
nur eine kuratierte Auswahl ("Typische Unterkünfte"). Die *vollständige*,
paginierte Ergebnisliste kommt über eine interne BFF-API
(guest-website-frontend/api/v1/card-sections/srl-objects), die clientseitig
per POST aufgerufen wird und Session-Header (x-language, x-domain,
x-xsrf-token) sowie ein A/B-Experiment-Flags-Objekt im Body erfordert.

Großer Vorteil: Die API-Antwort enthält direkt alle relevanten Felder
(Koordinaten, Preis, Personen, Zimmer, Ausstattung) — kein zweiter Request
pro Detailseite nötig.

Ausführen:
    python -m scraper.olpenitz_scraper
"""
import asyncio
import base64
import logging
import os
import re
import sys
import urllib.parse

from playwright.async_api import async_playwright

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
PAGE_SIZE   = 24

# Region-Pfad für Olpenitz (Unterregion von Kappeln/Schlei)
RESULTS_PATH = "/europa/deutschland/kappeln/kappeln/olpenitz/ergebnisse/"
RESULTS_URL  = BASE_URL + RESULTS_PATH
API_URL      = f"{BASE_URL}/guest-website-frontend/api/v1/card-sections/srl-objects"

# A/B-Experiment-Flags — Server validiert das Schema strikt, Inhalt ist irrelevant
# für die Suchergebnisse selbst (steuert nur UI-Varianten der Webseite).
EXPERIMENT_BODY = (
    '{"ssap":{"experimentVersion":5,"activeVariant":1},"btsr":{"experimentVersion":1,"activeVariant":0},'
    '"pdpe":{"experimentVersion":7,"activeVariant":1},"pdpr":{"experimentVersion":3,"activeVariant":0},'
    '"grid":{"experimentVersion":3,"activeVariant":0},"flex":{"experimentVersion":7,"activeVariant":0},'
    '"rpac":{"experimentVersion":5,"activeVariant":0},"sfrt":{"experimentVersion":5,"activeVariant":1},'
    '"lshc":{"experimentVersion":4,"activeVariant":0},"pdps":{"experimentVersion":2,"activeVariant":0},'
    '"spre":{"experimentVersion":12,"activeVariant":1},"msbv":{"experimentVersion":9,"activeVariant":1},'
    '"chdv":{"experimentVersion":9,"activeVariant":0},"vtpd":{"experimentVersion":4,"activeVariant":0},'
    '"chnv":{"experimentVersion":2,"activeVariant":0},"pchg":{"experimentVersion":3,"activeVariant":1},'
    '"titv":{"experimentVersion":6,"activeVariant":0},"isfv":{"experimentVersion":3,"activeVariant":0},'
    '"elsw":{"experimentVersion":3,"activeVariant":0},"dmvv":{"experimentVersion":3,"activeVariant":0},'
    '"cent":{"experimentVersion":4,"activeVariant":0},"srlv":{"experimentVersion":12,"activeVariant":0},'
    '"dbvv":{"experimentVersion":4,"activeVariant":0},"hpps":{"experimentVersion":2,"activeVariant":0},'
    '"rsch":{"experimentVersion":1,"activeVariant":0},"irmn":{"experimentVersion":21,"activeVariant":2},'
    '"lapd":{"experimentVersion":5,"activeVariant":1},"chme":{"experimentVersion":7,"activeVariant":0},'
    '"dbpv":{"experimentVersion":3,"activeVariant":1},"gvak":{"experimentVersion":7,"activeVariant":1},'
    '"dsbf":{"experimentVersion":7,"activeVariant":0},"hpwc":{"experimentVersion":8,"activeVariant":1},'
    '"pdpb":{"experimentVersion":1,"activeVariant":0},"dcbv":{"experimentVersion":1,"activeVariant":0},'
    '"oshv":{"experimentVersion":6,"activeVariant":0},"nypd":{"experimentVersion":7,"activeVariant":0},'
    '"dibu":{"experimentVersion":4,"activeVariant":0},"rvli":{"experimentVersion":4,"activeVariant":1},'
    '"lsav":{"experimentVersion":7,"activeVariant":1},"expe":{"experimentVersion":5,"activeVariant":0},'
    '"bbpv":{"experimentVersion":7,"activeVariant":1},"slsh":{"experimentVersion":4,"activeVariant":1},'
    '"isce":{"experimentVersion":11,"activeVariant":0},"hprv":{"experimentVersion":5,"activeVariant":1},'
    '"btfv":{"experimentVersion":3,"activeVariant":1},"bbsr":{"experimentVersion":3,"activeVariant":1},'
    '"lspa":{"experimentVersion":4,"activeVariant":1},"lsdk":{"experimentVersion":3,"activeVariant":0},'
    '"chat":{"experimentVersion":6,"activeVariant":0}}'
)

FILTER_B64 = urllib.parse.quote(base64.b64encode(RESULTS_PATH.encode()).decode())


def _price_per_night(price: dict) -> float | None:
    """`notFormattedPrice` ist ein 'ab'-Gesamtpreis für den Zeitraum in `unit`
    (meist '7 Nächte'), kein Nachtpreis. Durch die Nächte-Anzahl teilen für
    den echten (günstigsten verfügbaren) Preis pro Nacht."""
    total = price.get("notFormattedPrice")
    if total is None:
        return None
    unit = price.get("unit") or ""
    m = re.search(r"(\d+)", unit)
    nights = int(m.group(1)) if m else 1
    return round(total / nights, 2) if nights else None


def _parse_object(obj: dict) -> dict | None:
    """Wandelt ein API-Objekt direkt in unser Datenmodell um — keine Detailseite nötig."""
    name = obj.get("title")
    if not name:
        return None

    loc = obj.get("location") or {}
    stats = obj.get("stats") or {}
    price = obj.get("price") or {}
    breadcrumbs = obj.get("breadcrumbs") or []
    images = obj.get("images") or []

    # Ort = letzter Breadcrumb-Eintrag (granularste Ortsangabe, z.B. "Olpenitz")
    ort = breadcrumbs[-1]["label"] if breadcrumbs else "Olpenitz"

    equip = obj.get("generalEquipments") or {}
    ausstattung = ", ".join(k for k, v in equip.items() if v) or None

    seo_href = obj.get("seoHref") or f"/{obj['id']}/"

    # Erstes Bild = Titelbild (von der Plattform selbst so sortiert)
    bild_url = images[0].get("thumbnail") or images[0].get("url") if images else None

    return {
        "source_id":    str(obj["id"]),
        "source":       SOURCE_NAME,
        "url":          f"{BASE_URL}{seo_href}",
        "bild_url":     bild_url,
        "name":         name.strip(),
        "ort":          ort,
        "region":       "Schlei",
        "latitude":     loc.get("latitude"),
        "longitude":    loc.get("longitude"),
        "personen_max": stats.get("maxPersons") or stats.get("personCount"),
        "zimmer":       stats.get("bedrooms"),
        "badezimmer":   stats.get("bathrooms"),
        "ausstattung":  ausstattung,
        "preis_nacht":  _price_per_night(price),
    }


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


async def _fetch_page(page, page_num: int) -> dict:
    offset = (page_num - 1) * PAGE_SIZE
    resp = await page.request.post(
        f"{API_URL}?filter={FILTER_B64}&page={page_num}&pageSize={PAGE_SIZE}&offset={offset}",
        data=EXPERIMENT_BODY,
        headers={
            "content-type": "application/json;charset=UTF-8",
            "accept": "application/json, text/plain, */*",
            "x-language": "de_DE",
            "x-domain": "traum-ferienwohnungen.de",
            "referer": RESULTS_URL,
        },
    )
    if not resp.ok:
        log.warning(f"  Seite {page_num}: HTTP {resp.status}")
        return {}
    return await resp.json()


async def run_scraper():
    init_db()
    db = SessionLocal()

    log.info("=" * 60)
    log.info("Olpenitz-Scraper (echte Such-API, vollständige Ergebnisliste)")
    log.info("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Einmal die Seite laden, um die Session (Cookies/XSRF) zu etablieren
        await page.goto(RESULTS_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)

        # Erste Seite holen, um die Gesamtanzahl zu erfahren
        first = await _fetch_page(page, 1)
        section = first.get("data", {}).get("primarySection", {})
        heading = section.get("heading", "")
        objects = section.get("objects", [])
        log.info(f"Gefunden: {heading}")

        total_new = total_upd = total_geo = total_err = 0

        def _store(objs: list) -> None:
            nonlocal total_new, total_upd, total_geo, total_err
            for obj in objs:
                data = _parse_object(obj)
                if not data:
                    total_err += 1
                    continue
                has_geo = data["latitude"] is not None
                listing, neu = _save_listing(db, data)
                total_geo += int(has_geo)
                total_new += int(neu)
                total_upd += int(not neu)

        _store(objects)
        page_num = 1
        total_seen = len(objects)

        # Solange weitere Seiten Objekte liefern, weiter paginieren
        while objects:
            page_num += 1
            await asyncio.sleep(1.5)  # höflich bleiben
            result = await _fetch_page(page, page_num)
            objects = result.get("data", {}).get("primarySection", {}).get("objects", [])
            if not objects:
                break
            _store(objects)
            total_seen += len(objects)
            log.info(f"Seite {page_num}: +{len(objects)} (gesamt {total_seen})")

        await browser.close()

    db.close()
    log.info("=" * 60)
    log.info(f"Fertig — Neu: {total_new} | Update: {total_upd} | "
             f"mit Geo: {total_geo}/{total_seen} | Übersprungen: {total_err}")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_scraper())
