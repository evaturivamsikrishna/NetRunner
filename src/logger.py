# src/logger.py
"""
Ultra-verbose structured logger for NetRunner.
Provides:
 - Colored console output (disabled in CI)
 - Rotating log files (info + debug)
 - TRACE-level (custom below DEBUG)
 - Phase markers, boundaries, timing logs
 - Child loggers per module (main.checker, main.locale, etc.)
"""

import logging
import logging.handlers
import os
import sys
import json
import time

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

LOG_ROOT = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_ROOT, exist_ok=True)

INFO_LOG = os.path.join(LOG_ROOT, "netrunner_info.log")
DEBUG_LOG = os.path.join(LOG_ROOT, "netrunner_debug.log")

ENABLE_COLOR = os.getenv("CI", "false").lower() != "true"

# Custom TRACE level (below DEBUG)
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kws)

logging.Logger.trace = trace


# -------------------------------------------------------------------
# COLOR FORMATTING
# -------------------------------------------------------------------

COLOR = {
    "grey": "\x1b[38;21m",
    "yellow": "\x1b[33;21m",
    "red": "\x1b[31;21m",
    "cyan": "\x1b[36;21m",
    "green": "\x1b[32;21m",
    "bold": "\x1b[1m",
    "reset": "\x1b[0m",
}

def colorize(level, message):
    if not ENABLE_COLOR:
        return message
    if level >= logging.ERROR:
        return f"{COLOR['red']}{message}{COLOR['reset']}"
    elif level >= logging.WARNING:
        return f"{COLOR['yellow']}{message}{COLOR['reset']}"
    elif level >= logging.INFO:
        return f"{COLOR['green']}{message}{COLOR['reset']}"
    elif level >= logging.DEBUG:
        return f"{COLOR['cyan']}{message}{COLOR['reset']}"
    else:
        return f"{COLOR['grey']}{message}{COLOR['reset']}"


class ColorFormatter(logging.Formatter):
    def format(self, record):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        lvl = record.levelname
        msg = record.getMessage()

        colored = colorize(record.levelno, f"{ts} [{lvl}] {record.name}: {msg}")
        return colored


class JsonFormatter(logging.Formatter):
    """Optional structured logs for debug.log."""
    def format(self, record):
        payload = {
            "timestamp": record.created,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "file": record.pathname,
            "line": record.lineno,
        }
        return json.dumps(payload)


# -------------------------------------------------------------------
# LOGGER FACTORY
# -------------------------------------------------------------------

def get_logger(name="netrunner", level="INFO"):
    logger = logging.getLogger(name)

    # Avoid double-attaching handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # full pipeline logs always enabled

    # ------------------------------
    # Console Handler
    # ------------------------------
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)

    # ------------------------------
    # Info Rotating Log
    # ------------------------------
    ih = logging.handlers.RotatingFileHandler(
        INFO_LOG, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    ih.setLevel(logging.INFO)
    ih.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
    logger.addHandler(ih)

    # ------------------------------
    # Debug Rotating Log (JSON structured)
    # ------------------------------
    dh = logging.handlers.RotatingFileHandler(
        DEBUG_LOG, maxBytes=15_000_000, backupCount=5, encoding="utf-8"
    )
    dh.setLevel(logging.DEBUG)
    dh.setFormatter(JsonFormatter())
    logger.addHandler(dh)

    logger.info("🔧 Logger initialized for '%s'", name)
    return logger


# -------------------------------------------------------------------
# UTILITY SHORTCUTS
# -------------------------------------------------------------------

def phase(logger, name):
    """Visual marker for pipeline sections."""
    logger.info("══════════════════════════════════════════════")
    logger.info(f"📍 Entering phase: {name}")
    logger.info("══════════════════════════════════════════════")


def event(logger, name, **data):
    """Machine-parsable event."""
    logger.debug("EVENT %s | %s", name, json.dumps(data))


def timing(logger, label, start_time):
    elapsed = round(time.time() - start_time, 3)
    logger.info("⏱ %s: %ss", label, elapsed)