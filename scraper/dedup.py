"""
Deduplizierung und Datenbereinigung der Listings-Datenbank.

Ausführen:
    python -m scraper.dedup
"""
import logging
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import Listing, Preis

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _normalize_name(name: str) -> str:
    """Kleinschreibung, Whitespace-Normalisierung für Vergleich."""
    return re.sub(r"\s+", " ", name.strip().lower())


def remove_exact_duplicates(db) -> int:
    """
    Entfernt Duplikate mit identischer source_id (kann bei Scraper-Fehlern entstehen).
    Behält jeweils den ältesten Eintrag.
    """
    seen: dict[str, int] = {}
    removed = 0
    for listing in db.query(Listing).order_by(Listing.erstellt_am).all():
        key = listing.source_id
        if key in seen:
            log.info(f"  Duplikat entfernt: id={listing.id} source_id={key!r}")
            db.query(Preis).filter(Preis.listing_id == listing.id).delete()
            db.delete(listing)
            removed += 1
        else:
            seen[key] = listing.id
    db.commit()
    return removed


def flag_similar_names(db) -> list[tuple]:
    """
    Findet Listings mit sehr ähnlichem Namen und gleichem Ort — gibt sie zur
    manuellen Prüfung zurück (löscht nichts automatisch).
    """
    listings = db.query(Listing).all()
    seen: dict[str, list] = {}
    for l in listings:
        key = (_normalize_name(l.name or ""), (l.ort or "").lower())
        seen.setdefault(key, []).append(l)

    suspects = [(key, group) for key, group in seen.items() if len(group) > 1]
    return suspects


def clean_whitespace(db) -> int:
    """Entfernt führende/nachfolgende Leerzeichen in Name und Ort."""
    updated = 0
    for l in db.query(Listing).all():
        changed = False
        if l.name and l.name != l.name.strip():
            l.name = l.name.strip()
            changed = True
        if l.ort and l.ort != l.ort.strip():
            l.ort = l.ort.strip()
            changed = True
        if changed:
            updated += 1
    db.commit()
    return updated


def run_cleanup():
    db = SessionLocal()
    try:
        log.info("=== Datenbereinigung gestartet ===")

        n = clean_whitespace(db)
        log.info(f"Whitespace bereinigt: {n} Einträge")

        n = remove_exact_duplicates(db)
        log.info(f"Exakte Duplikate entfernt: {n}")

        suspects = flag_similar_names(db)
        if suspects:
            log.warning(f"{len(suspects)} mögliche Duplikate (gleicher Name+Ort):")
            for (name, ort), group in suspects:
                ids = [l.id for l in group]
                log.warning(f"  Name={name!r} Ort={ort!r} → IDs {ids}")
        else:
            log.info("Keine ähnlichen Duplikate gefunden.")

        log.info("=== Bereinigung abgeschlossen ===")
    finally:
        db.close()


if __name__ == "__main__":
    run_cleanup()
