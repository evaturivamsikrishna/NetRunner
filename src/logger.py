import logging
from logging.handlers import RotatingFileHandler, SMTPHandler
import os
import sys
from datetime import datetime

# ============================================================
# 🧠 CONFIGURATION
# ============================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "monitor.log")
ERROR_LOG = os.path.join(LOG_DIR, "errors.log")

# Optional email alert configuration (disabled by default)
ENABLE_EMAIL_ALERTS = False
SMTP_CONFIG = {
    "mailhost": ("smtp.gmail.com", 587),
    "fromaddr": os.getenv("LOG_EMAIL_FROM", ""),
    "toaddrs": [os.getenv("LOG_EMAIL_TO", "")],
    "subject": "⚠️ Website Monitor Alert",
    "credentials": (os.getenv("LOG_EMAIL_FROM", ""), os.getenv("LOG_EMAIL_PASSWORD", "")),
    "secure": ()
}


# ============================================================
# 🎯 LOGGER INITIALIZATION
# ============================================================
def get_logger(name="website-monitor", log_level=logging.INFO):
    """Advanced logger with console + file rotation + optional email alerts."""
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Prevent duplicate handlers during reuse
    if logger.handlers:
        return logger

    # --- FORMATTERS ---
    verbose_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"
    )

    # --- HANDLERS ---
    # Console output
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(console_fmt)

    # Rotating file handler (general)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(verbose_fmt)

    # Error-specific log
    eh = RotatingFileHandler(ERROR_LOG, maxBytes=3_000_000, backupCount=5, encoding="utf-8")
    eh.setLevel(logging.ERROR)
    eh.setFormatter(verbose_fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)
    logger.addHandler(eh)

    # --- OPTIONAL EMAIL ALERTS ---
    if ENABLE_EMAIL_ALERTS and SMTP_CONFIG["fromaddr"] and SMTP_CONFIG["toaddrs"]:
        try:
            mail_handler = SMTPHandler(
                mailhost=SMTP_CONFIG["mailhost"],
                fromaddr=SMTP_CONFIG["fromaddr"],
                toaddrs=SMTP_CONFIG["toaddrs"],
                subject=SMTP_CONFIG["subject"],
                credentials=SMTP_CONFIG["credentials"],
                secure=SMTP_CONFIG["secure"],
            )
            mail_handler.setLevel(logging.CRITICAL)
            mail_handler.setFormatter(verbose_fmt)
            logger.addHandler(mail_handler)
        except Exception as e:
            print(f"[WARN] Failed to configure SMTP logging: {e}")

    # --- TEST MESSAGE (optional) ---
    logger.debug(f"Logger initialized at {datetime.utcnow().isoformat()} UTC")
    return logger