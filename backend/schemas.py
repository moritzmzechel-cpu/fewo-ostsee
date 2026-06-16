from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


# ── Preis ─────────────────────────────────────────────────────────────────────

class PreisBase(BaseModel):
    preis_pro_nacht: Optional[float] = None
    preis_pro_woche: Optional[float] = None
    waehrung: str = "EUR"


class PreisCreate(PreisBase):
    pass


class PreisOut(PreisBase):
    id: int
    listing_id: int
    erfasst_am: datetime

    model_config = {"from_attributes": True}


# ── Listing ────────────────────────────────────────────────────────────────────

class ListingBase(BaseModel):
    name: str
    ort: str
    region: str = "Schlei"
    url: Optional[str] = None
    bild_url: Optional[str] = None
    source: str = "traum-ferienwohnungen"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    personen_max: Optional[int] = None
    zimmer: Optional[int] = None
    badezimmer: Optional[int] = None
    haustiere: Optional[str] = None
    ausstattung: Optional[str] = None


class ListingCreate(ListingBase):
    source_id: str


class ListingOut(ListingBase):
    id: int
    source_id: str
    erstellt_am: datetime
    aktualisiert_am: datetime
    preise: List[PreisOut] = []

    model_config = {"from_attributes": True}


class ListingShort(BaseModel):
    """Kompakte Darstellung für Listenansicht."""
    id: int
    name: str
    ort: str
    region: str
    bild_url: Optional[str] = None
    personen_max: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    letzter_preis_nacht: Optional[float] = None

    model_config = {"from_attributes": True}
