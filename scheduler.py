"""
Täglicher Scraper-Scheduler.

Ausführen (läuft dauerhaft im Hintergrund):
    python scheduler.py

Oder einmalig sofort:
    python scheduler.py --now
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime

import schedule
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Uhrzeit für den täglichen Lauf (z.B. 03:00 nachts — wenig Traffic)
DAILY_RUN_AT = "03:00"


def run_scraper_job():
    log.info(f"Scheduler: Starte Scraper-Lauf — {datetime.now():%Y-%m-%d %H:%M}")
    from scraper.traum_fw_scraper import run_scraper
    try:
        asyncio.run(run_scraper())
        log.info("Scheduler: Lauf erfolgreich abgeschlossen.")
    except Exception as e:
        log.error(f"Scheduler: Fehler beim Scraper-Lauf: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="Sofort einmalig ausführen")
    args = parser.parse_args()

    if args.now:
        log.info("--now: Starte sofortigen Lauf.")
        run_scraper_job()
        return

    log.info(f"Scheduler aktiv — täglicher Lauf um {DAILY_RUN_AT} Uhr.")
    schedule.every().day.at(DAILY_RUN_AT).do(run_scraper_job)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
