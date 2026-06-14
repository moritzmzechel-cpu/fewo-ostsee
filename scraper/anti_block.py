"""
Anti-Blocking-Maßnahmen für den Scraper.
Ziel: Normales Nutzerverhalten simulieren, kein aggressives Crawlen.
"""
import asyncio
import random
from typing import Optional

# Realistische Browser-User-Agents (Chrome/Firefox, Windows/Mac, aktuell)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# Viewport-Variationen (wirkt natürlicher als immer 1920×1080)
VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 800},
    {"width": 1536, "height": 864},
]


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def random_viewport() -> dict:
    return random.choice(VIEWPORTS)


async def polite_delay(min_s: float = 3.0, max_s: float = 8.0) -> None:
    """Zufällige Pause zwischen Requests — simuliert menschliches Lesen."""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)


async def short_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
    """Kurze Pause (z.B. zwischen Scroll-Aktionen auf einer Seite)."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def simulate_human_scroll(page) -> None:
    """Scrollt die Seite langsam nach unten — wirkt menschlicher."""
    total_height = await page.evaluate("document.body.scrollHeight")
    steps = random.randint(3, 6)
    for i in range(1, steps + 1):
        target = int(total_height * (i / steps))
        await page.evaluate(f"window.scrollTo(0, {target})")
        await short_delay(0.3, 0.9)
    # Am Ende wieder nach oben (natürliches Verhalten)
    await page.evaluate("window.scrollTo(0, 0)")


def get_browser_context_args(user_agent: Optional[str] = None) -> dict:
    """Playwright-Browser-Kontext-Parameter für maximale Tarnung."""
    ua = user_agent or random_user_agent()
    vp = random_viewport()
    return {
        "user_agent": ua,
        "viewport": vp,
        "locale": "de-DE",
        "timezone_id": "Europe/Berlin",
        "geolocation": None,
        "permissions": [],
        "extra_http_headers": {
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "DNT": "1",
        },
    }


# Sicherheitsgrenzen für einen Scraping-Lauf
MAX_LISTINGS_PER_RUN = 80    # Danach Pause / VPN-Wechsel empfohlen
MAX_PAGES_PER_RUN    = 10    # Suchseiten (je ~10 Listings)
REQUEST_TIMEOUT_MS   = 30_000
