# src/analytics/metrics_builder.py
"""
Simple metrics builder.
Reads per-locale summary_history_{locale}.csv files in data/reports/
Produces a single data/dashboard/generated/metrics.json file.

This is intentionally minimal and deterministic so CI can rely on it.
"""
import os
import glob
import json
import logging
from collections import defaultdict
from datetime import datetime

import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)

ROOT = os.getcwd()
REPORTS_DIR = os.path.join(ROOT, "data", "reports")
OUT_DIR = os.path.join(ROOT, "data", "dashboard", "generated")
OUT_PATH = os.path.join(OUT_DIR, "metrics.json")


def _gather_locale_summaries():
    files = glob.glob(os.path.join(REPORTS_DIR, "summary_history_*.csv"))
    out = {}
    for fn in files:
        try:
            df = pd.read_csv(fn)
            if df.empty:
                continue
            locale = os.path.basename(fn).split("summary_history_")[-1].replace(".csv", "")
            # Keep last 14 runs only for compactness
            df = df.sort_values("run_time").tail(14)
            series = []
            for _, r in df.iterrows():
                series.append({
                    "run_time": r.get("run_time"),
                    "pages_checked": int(r.get("pages_checked", 0)),
                    "total_links_found": int(r.get("total_links_found", 0)),
                    "unique_links": int(r.get("unique_links", 0)),
                    "broken_links": int(r.get("broken_links", 0)),
                    "duration_mins": float(r.get("duration_mins", 0)),
                    "success_rate": float(r.get("success_rate", 0)),
                    "status": r.get("status", "")
                })
            out[locale] = {
                "latest_run": series[-1]["run_time"] if series else None,
                "series": series,
                "summary": series[-1] if series else {}
            }
        except Exception as e:
            logger.exception("Failed to parse %s: %s", fn, e)
    return out


def build_metrics():
    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "global": {},
        "locales": {}
    }

    locale_data = _gather_locale_summaries()
    payload["locales"] = locale_data

    # Global rollup
    total_runs = 0
    total_links = 0
    total_broken = 0
    for loc, ld in locale_data.items():
        s = ld.get("summary") or {}
        total_runs += 1 if s else 0
        total_links += int(s.get("total_links_found", 0) or 0)
        total_broken += int(s.get("broken_links", 0) or 0)

    payload["global"] = {
        "total_runs": total_runs,
        "total_links_checked": total_links,
        "total_broken_links": total_broken,
        "overall_success_rate": round(100 - ((total_broken / total_links) * 100) if total_links else 100, 2)
    }

    # write single canonical metrics.json (no timestamp suffix)
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.info("✅ Metrics successfully generated -> %s", OUT_PATH)
    except Exception as e:
        logger.exception("Failed to write metrics.json: %s", e)

    return OUT_PATH