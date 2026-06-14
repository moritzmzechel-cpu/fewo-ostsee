from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Listing(Base):
    """Einzelne Ferienwohnung."""
    __tablename__ = "listings"

    id              = Column(Integer, primary_key=True, index=True)
    source_id       = Column(String, unique=True, index=True)   # ID auf der Quell-Plattform
    source          = Column(String, default="traum-ferienwohnungen")
    url             = Column(String)

    # Kerndaten
    name            = Column(String)
    ort             = Column(String)
    region          = Column(String, default="Schlei")
    strasse         = Column(String, nullable=True)

    # Geo
    latitude        = Column(Float, nullable=True)
    longitude       = Column(Float, nullable=True)

    # Kapazität & Ausstattung
    personen_max    = Column(Integer, nullable=True)
    zimmer          = Column(Integer, nullable=True)
    badezimmer      = Column(Integer, nullable=True)
    haustiere       = Column(String, nullable=True)   # "ja" / "nein" / "auf Anfrage"
    ausstattung     = Column(Text, nullable=True)     # kommaseparierte Tags

    # Metadaten
    erstellt_am     = Column(DateTime, default=datetime.utcnow)
    aktualisiert_am = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    preise          = relationship("Preis", back_populates="listing",
                                   cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Listing id={self.id} name={self.name!r} ort={self.ort!r}>"


class Preis(Base):
    """Preis-Snapshot einer Ferienwohnung (Zeitreihe)."""
    __tablename__ = "preise"

    id              = Column(Integer, primary_key=True, index=True)
    listing_id      = Column(Integer, ForeignKey("listings.id"), index=True)

    preis_pro_nacht = Column(Float, nullable=True)   # EUR
    preis_pro_woche = Column(Float, nullable=True)   # EUR
    waehrung        = Column(String, default="EUR")
    erfasst_am      = Column(DateTime, default=datetime.utcnow)

    listing         = relationship("Listing", back_populates="preise")

    def __repr__(self):
        return (f"<Preis listing_id={self.listing_id} "
                f"nacht={self.preis_pro_nacht} erfasst={self.erfasst_am:%Y-%m-%d}>")
