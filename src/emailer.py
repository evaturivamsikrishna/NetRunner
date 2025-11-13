# src/emailer.py
"""
Simple production-ready emailer for NetRunner.
Uses environment variables for SMTP config:
  - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, SMTP_TO (comma-separated)
Optional:
  - SMTP_TLS (default true)
This module does not fail hard if email config missing — it logs and moves on.
"""
import os
import smtplib
import logging
from email.message import EmailMessage
from typing import Optional

from src.logger import get_logger

logger = get_logger(__name__)


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


def send_summary(subject: str, body: str, html: str = None) -> bool:
    host = _get_env("SMTP_HOST")
    port = int(_get_env("SMTP_PORT", "587"))
    user = _get_env("SMTP_USER")
    pwd = _get_env("SMTP_PASS")
    from_addr = _get_env("SMTP_FROM")
    to_addrs = _get_env("SMTP_TO")

    if not (host and from_addr and to_addrs):
        logger.info("Email config missing — skipping send_summary.")
        return False

    to_list = [s.strip() for s in to_addrs.split(",") if s.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    use_tls = _get_env("SMTP_TLS", "true").lower() != "false"

    try:
        logger.info("Connecting to SMTP %s:%s", host, port)
        with smtplib.SMTP(host, port, timeout=20) as s:
            if use_tls:
                s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)
        logger.info("Email sent to %s", to_list)
        return True
    except Exception as e:
        logger.exception("Failed to send email: %s", e)
        return False