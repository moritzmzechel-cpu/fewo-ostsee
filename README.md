# FeWo Ostsee SH — Setup & Start

## Voraussetzungen
- Python 3.11+ → https://python.org/downloads
- Git → https://git-scm.com

---

## 1. Einmaliges Setup (PowerShell / CMD)

```powershell
# Ins Projektverzeichnis wechseln
cd fewo-ostsee

# Virtuelle Umgebung anlegen & aktivieren
python -m venv .venv
.venv\Scripts\activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Playwright-Browser installieren (nur einmal nötig, ~150 MB)
playwright install chromium
```

---

## 2. Backend starten

```powershell
# Virtuelle Umgebung aktivieren (falls noch nicht aktiv)
.venv\Scripts\activate

# API-Server starten
uvicorn backend.main:app --reload --port 8000
```

API ist dann erreichbar unter:
- http://localhost:8000          → Status
- http://localhost:8000/docs     → Swagger-Dokumentation (interaktiv!)
- http://localhost:8000/listings → Alle Ferienwohnungen

---

## 3. Scraper ausführen

> Empfehlung: ProtonVPN vorher aktivieren (Netherlands-Server)

```powershell
# Neue PowerShell-Fenster öffnen, venv aktivieren
.venv\Scripts\activate

# Scraper starten
python -m scraper.traum_fw_scraper
```

Der Scraper läuft ~15–30 Minuten für 80 Listings.
Fortschritt wird im Terminal angezeigt.

---

## 4. Datenbank ansehen (optional)

```powershell
pip install sqlite-utils
sqlite-utils tables fewo.db        # Tabellen anzeigen
sqlite-utils rows fewo.db listings # Einträge anzeigen
```

Oder: DB Browser for SQLite (GUI) → https://sqlitebrowser.org

---

## Projektstruktur

```
fewo-ostsee/
├── backend/
│   ├── main.py        # FastAPI App
│   ├── models.py      # Datenbank-Modelle
│   ├── database.py    # SQLite-Verbindung
│   ├── schemas.py     # API-Datenformate
│   └── routers/
│       └── listings.py
├── scraper/
│   ├── traum_fw_scraper.py   # Hauptscraper
│   └── anti_block.py         # IP-Schutz-Maßnahmen
├── frontend/          # (ab Phase 3)
├── fewo.db            # SQLite-Datenbank (wird automatisch erstellt)
└── requirements.txt
```

---

## IP-Schutz Checkliste

- [x] Playwright simuliert echten Browser (kein einfaches HTTP)
- [x] Zufällige Pausen 3–8 Sekunden zwischen Requests
- [x] Maximale 80 Listings pro Lauf
- [x] Rotierende User-Agents & Viewports
- [ ] ProtonVPN aktivieren vor längeren Läufen (empfohlen)
