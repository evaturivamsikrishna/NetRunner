"""
src/locales/loader.py

Central source of truth for locale configuration.
Loads data/locales.json when present, otherwise falls back to DEFAULT_LOCALES.
"""

import os
import json
from src.locales.constants import DEFAULT_LOCALES
from src.logger import get_logger

logger = get_logger("locales.loader")

LOCALES_JSON_PATH = os.path.join("data", "locales.json")


# -------------------------------------------------
# Load locales.json (or fallback)
# -------------------------------------------------
def load_locales_config():
    """
    Returns dict:
      {
         "locales": { "en": "", "es": "es-es", ... },
         "released": ["en","es","de",...]
      }
    """
    if os.path.exists(LOCALES_JSON_PATH):
        try:
            with open(LOCALES_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            locales = data.get("locales", {})
            released = data.get("released", list(locales.keys()))

            logger.info(f"Loaded {len(locales)} locales from locales.json")
            return {"locales": locales, "released": released}

        except Exception as e:
            logger.error(f"Failed reading locales.json: {e}")

    # Fallback
    logger.warning("Using DEFAULT_LOCALES fallback (locales.json missing or invalid).")
    return {
        "locales": DEFAULT_LOCALES,
        "released": list(DEFAULT_LOCALES.keys())
    }


# -------------------------------------------------
# Resolve enabled locales cleanly
# -------------------------------------------------
def resolved_enabled_locales(cfg: dict) -> list:
    """
    Return list of locale codes to run.

    cfg must be a dict returned by load_locales_config()

    Always respects:
    - locales present
    - released list (if present)
    """
    if not cfg:
        logger.error("resolved_enabled_locales() called with empty config.")
        return []

    locales = cfg.get("locales", {})
    released = cfg.get("released", list(locales.keys()))

    enabled = sorted(released)

    logger.info(f"Enabled locales resolved: {enabled}")
    return enabled