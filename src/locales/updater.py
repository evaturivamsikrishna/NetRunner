# src/locales/updater.py
"""
Fetch locales from live site language switcher and write data/locales.json.
Safe: if it fails we keep existing file.
"""
import requests
from bs4 import BeautifulSoup
import json
import os
from src.logger import get_logger

logger = get_logger("locales.updater")
ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "data")
OUT_PATH = os.path.join(DATA_DIR, "locales.json")
SITE_ROOT = "https://kwalee.com"

def fetch_language_switcher():
    try:
        r = requests.get(SITE_ROOT, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # naive: find <select id="lang-switch"> or nav .lang list — fallback safe
        mapping = {}
        # look for <a> inside language switcher link areas
        for a in soup.select("a"):
            href = a.get("href") or ""
            text = (a.get_text() or "").strip()
            if "/en" in href or "/es" in href or "/de" in href:
                # crude heuristic
                path = href.split(SITE_ROOT)[-1].strip("/")
                code = path.split("/")[0] if path else ""
                if code:
                    mapping[code] = path
        # fallback: if mapping empty, return None
        return mapping or None
    except Exception as e:
        logger.warning("locale fetch failed: %s", e)
        return None

def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info("Fetching live locales from %s", SITE_ROOT)
    mapping = fetch_language_switcher()
    if not mapping:
        logger.info("No mapping found — leaving locales.json untouched.")
        return False
    out = {
        "enabled_locales": list(mapping.keys()),
        "locales_map": mapping
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    logger.info("Wrote locales.json with %d locales.", len(mapping))
    return True

if __name__ == "__main__":
    run()