from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///./fewo.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # nötig für SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI Dependency — gibt DB-Session zurück und schließt sie danach."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Erstellt alle Tabellen (idempotent)."""
    from . import models  # noqa: F401  — stellt sicher dass Modelle registriert sind
    Base.metadata.create_all(bind=engine)
