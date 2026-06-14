from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from ..database import get_db
from ..models import Listing, Preis
from ..schemas import ListingOut, ListingCreate, ListingShort, PreisCreate

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("/", response_model=List[ListingShort])
def get_listings(
    ort: Optional[str] = Query(None, description="Filter nach Ort"),
    min_personen: Optional[int] = Query(None),
    max_personen: Optional[int] = Query(None),
    min_preis: Optional[float] = Query(None, description="Mindestpreis pro Nacht (EUR)"),
    max_preis: Optional[float] = Query(None, description="Maximalpreis pro Nacht (EUR)"),
    haustiere: Optional[bool] = Query(None, description="true = Haustiere erlaubt"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """Alle Ferienwohnungen — mit optionalen Filtern."""
    q = db.query(Listing)
    if ort:
        q = q.filter(Listing.ort.ilike(f"%{ort}%"))
    if min_personen:
        q = q.filter(Listing.personen_max >= min_personen)
    if max_personen:
        q = q.filter(Listing.personen_max <= max_personen)
    if haustiere is True:
        q = q.filter(Listing.haustiere == "ja")
    elif haustiere is False:
        q = q.filter(Listing.haustiere != "ja")

    listings = q.offset(offset).limit(limit).all()

    # Preis-Filter nachgelagert (Preis liegt in separater Tabelle)
    if min_preis is not None or max_preis is not None:
        filtered = []
        for l in listings:
            letzter = (
                db.query(Preis)
                .filter(Preis.listing_id == l.id)
                .order_by(Preis.erfasst_am.desc())
                .first()
            )
            preis = letzter.preis_pro_nacht if letzter else None
            if preis is None:
                continue
            if min_preis is not None and preis < min_preis:
                continue
            if max_preis is not None and preis > max_preis:
                continue
            filtered.append(l)
        listings = filtered

    result = []
    for l in listings:
        letzter_preis = (
            db.query(Preis)
            .filter(Preis.listing_id == l.id)
            .order_by(Preis.erfasst_am.desc())
            .first()
        )
        item = ListingShort.model_validate(l)
        item.letzter_preis_nacht = letzter_preis.preis_pro_nacht if letzter_preis else None
        result.append(item)

    return result


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    """Detail-Ansicht einer Ferienwohnung inkl. Preisverlauf."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    return listing


@router.post("/", response_model=ListingOut, status_code=201)
def create_listing(data: ListingCreate, db: Session = Depends(get_db)):
    """Neue Ferienwohnung anlegen (wird vom Scraper genutzt)."""
    existing = db.query(Listing).filter(Listing.source_id == data.source_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="source_id bereits vorhanden")
    listing = Listing(**data.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.post("/{listing_id}/preise", status_code=201)
def add_preis(listing_id: int, data: PreisCreate, db: Session = Depends(get_db)):
    """Neuen Preis-Snapshot anhängen."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing nicht gefunden")
    preis = Preis(listing_id=listing_id, **data.model_dump())
    db.add(preis)
    db.commit()
    return {"ok": True, "id": preis.id}


@router.get("/stats/overview")
def stats_overview(db: Session = Depends(get_db)):
    """Einfache Kennzahlen für das Dashboard."""
    total = db.query(func.count(Listing.id)).scalar()
    orte  = db.query(func.count(func.distinct(Listing.ort))).scalar()
    mit_preis = (
        db.query(func.count(func.distinct(Preis.listing_id))).scalar()
    )
    avg_preis = db.query(func.avg(Preis.preis_pro_nacht)).scalar()

    return {
        "gesamt_listings": total,
        "orte": orte,
        "mit_preisdaten": mit_preis,
        "avg_preis_pro_nacht": round(avg_preis, 2) if avg_preis else None,
    }
