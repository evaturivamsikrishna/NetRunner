# src/main.py
#!/usr/bin/env python3
"""
src/main.py - NetRunner orchestrator (v12)
Run:
  python -m src.main --max-procs 4 --locales en,es,de
"""
import os
import sys
import time
import json
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Tuple, Dict, Any

import pandas as pd

from src.logger import get_logger
from src.analytics.metrics_builder import build_metrics
from src.checker import run_checker  # sync wrapper that runs async loop and returns tuple
from src.locales.loader import resolved_enabled_locales, load_locales_config

logger = get_logger(__name__)

ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "data")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
DASH_DIR = os.path.join(DATA_DIR, "dashboard")
GEN_DIR = os.path.join(DASH_DIR, "generated")
METRICS_PATH = os.path.join(GEN_DIR, "metrics.json")
LATEST_BROKEN = os.path.join(REPORTS_DIR, "broken_links_latest.csv")
DEFAULT_MAX_PROCS = int(os.getenv("MAX_PROCS", "4"))
BASE_URL = os.getenv("BASE_URL", "https://kwalee.com")


def find_locale_csvs() -> List[Tuple[str, str]]:
    out = []
    if not os.path.isdir(DATA_DIR):
        return out
    for fn in os.listdir(DATA_DIR):
        if fn.startswith("urls_to_check_") and fn.endswith(".csv"):
            locale = fn.split("urls_to_check_")[-1].replace(".csv", "")
            out.append((locale, os.path.join(DATA_DIR, fn)))
    return sorted(out, key=lambda x: x[0])


def read_urls(path: str) -> List[str]:
    try:
        df = pd.read_csv(path, header=None)
        return [str(u).strip() for u in df[0].tolist() if pd.notna(u)]
    except Exception as e:
        logger.exception("Failed to read URLs from %s: %s", path, e)
        return []


def check_locale_homepage(locale_code: str, locale_path_map: dict, base_url: str = BASE_URL, timeout: int = 10) -> bool:
    """
    locale_code = 'da'
    locale_path_map = { 'da': 'da-dk', 'es': 'es-es', 'en': '' }

    Returns True if homepage URL is alive.
    """

    # Fetch actual mapped locale path (fallback to raw key)
    path = locale_path_map.get(locale_code, locale_code)

    # Build homepage URL correctly
    if path == "":
        url = base_url.rstrip("/") + "/"
    else:
        url = f"{base_url.rstrip('/')}/{path}/"

    # --- Live check ---
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        code = resp.status_code

        if code in (200, 301, 302):
            logger.info(f"🌍 Locale {locale_code} OK → {url} ({code})")
            return True

        logger.warning(f"🌍 Locale {locale_code} homepage → {url} ({code}) → SKIP")
        return False

    except Exception as e:
        logger.warning(f"🌍 Locale {locale_code} homepage failed → {url} ({e})")
        return False


def compute_metrics(total_links: int, broken_links: int, unique_links: int, duration_sec: float) -> Dict[str, Any]:
    success_rate = 100 - ((broken_links / total_links) * 100 if total_links else 0)
    duplicate_count = total_links - unique_links
    efficiency = (unique_links / total_links * 100) if total_links else 0
    return {
        "success_rate": round(success_rate, 2),
        "duplicate_count": duplicate_count,
        "crawler_efficiency": round(efficiency, 2),
        "duration_mins": round(duration_sec / 60, 2),
    }


def process_locale_worker(locale: str, csv_path: str, reports_dir: str = REPORTS_DIR, base_url: str = BASE_URL) -> Dict[str, Any]:
    """
    Worker executed in separate process. Must be picklable (top-level).
    Returns summary dict for the locale.
    """
    t0 = time.time()
    logger_local = get_logger(f"worker.{locale}")
    logger_local.info("Starting worker for locale=%s, csv=%s", locale, csv_path)

    urls = []
    try:
        urls = read_urls(csv_path)
    except Exception as e:
        logger_local.exception("Failed to read urls for %s: %s", locale, e)
        return {"locale": locale, "status": "error", "error": str(e)}

    if not urls:
        logger_local.warning("No URLs for %s — skipping", locale)
        return {"locale": locale, "status": "skipped_no_urls", "pages_checked": 0}

    if not check_locale_homepage(locale, cfg["locales"], base_url=base_url):
        logger_local.info("Homepage unavailable for %s — skipping", locale)
        return {"locale": locale, "status": "skipped_homepage_unavailable", "pages_checked": 0}

    os.makedirs(reports_dir, exist_ok=True)

    try:
        # run_checker returns (broken_path, invalid_links, all_links, duration)
        broken_path, invalid_links, all_links, duration = run_checker(urls, output_dir=reports_dir)
    except Exception as e:
        logger_local.exception("run_checker failed for %s: %s", locale, e)
        return {"locale": locale, "status": "error", "error": str(e)}

    metrics = compute_metrics(len(all_links), len(invalid_links), len({l.get("url") for l in all_links}), duration)
    summary = {
        "run_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "locale": locale,
        "pages_checked": len(urls),
        "total_links_found": len(all_links),
        "unique_links": len({l.get("url") for l in all_links}),
        "duplicate_count": metrics["duplicate_count"],
        "crawler_efficiency": metrics["crawler_efficiency"],
        "broken_links": len(invalid_links),
        "duration_sec": round(duration, 2),
        "duration_mins": metrics["duration_mins"],
        "success_rate": metrics["success_rate"],
        "status": "✅ Healthy" if len(invalid_links) == 0 else f"⚠️ {len(invalid_links)} broken",
    }

    # append summary CSV
    try:
        summary_path = os.path.join(reports_dir, f"summary_history_{locale}.csv")
        import pandas as pd
        pd.DataFrame([summary]).to_csv(summary_path, mode="a", header=not os.path.exists(summary_path), index=False)
        logger_local.info("Wrote summary CSV %s", summary_path)
    except Exception:
        logger_local.exception("Failed to write summary CSV for %s", locale)

    logger_local.info("Completed locale=%s status=%s duration=%.2f mins", locale, summary["status"], summary["duration_mins"])
    return summary


def parse_args():
    p = argparse.ArgumentParser(description="NetRunner main runner")
    p.add_argument("--locales", help="comma separated locale list override (csv base names)", default=None)
    p.add_argument("--max-procs", type=int, default=DEFAULT_MAX_PROCS)
    p.add_argument("--skip-metrics", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()

    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(GEN_DIR, exist_ok=True)

    all_csvs = find_locale_csvs()
    if not all_csvs:
        logger.error("No urls_to_check_{locale}.csv files found under data/. Create them first.")
        return

    cfg = load_locales_config()
    enabled = resolved_enabled_locales(cfg)

    # CLI override
    if args.locales:
        allowed = set([s.strip() for s in args.locales.split(",") if s.strip()])
        logger.info("CLI override locales -> %s", sorted(allowed))
    else:
        allowed = set(enabled) if enabled else set([loc for loc, _ in all_csvs])
        logger.info("Locales to run -> %s", sorted(allowed))

    targets = [(loc, path) for loc, path in all_csvs if loc in allowed]
    if not targets:
        logger.error("After filtering, no locales to run. Exiting.")
        return

    start_all = time.time()
    results = {}
    logger.info("Starting processing with max_procs=%s", args.max_procs)

    with ProcessPoolExecutor(max_workers=args.max_procs) as exe:
        futures = {exe.submit(process_locale_worker, loc, path, REPORTS_DIR, BASE_URL): loc for loc, path in targets}
        for fut in as_completed(futures):
            loc = futures[fut]
            try:
                res = fut.result()
                results[loc] = res
                logger.info("Locale %s finished -> %s", loc, res.get("status"))
            except Exception as e:
                logger.exception("Locale %s failed: %s", loc, e)
                results[loc] = {"locale": loc, "status": "error", "error": str(e)}

    # run metrics builder
    if not args.skip_metrics:
        try:
            logger.info("Running metrics builder...")
            build_metrics()
        except Exception:
            logger.exception("metrics_builder failed")

    # write final metrics.json (single canonical file)
    try:
        payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "locales": results}
        with open(METRICS_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.info("Written metrics -> %s", METRICS_PATH)
    except Exception:
        logger.exception("Failed to write metrics.json")

    # inject latest broken links if exist
    if os.path.exists(LATEST_BROKEN):
        try:
            with open(LATEST_BROKEN, encoding="utf-8") as f:
                import csv
                broken = list(csv.DictReader(f))
            with open(METRICS_PATH, "r+", encoding="utf-8") as f:
                m = json.load(f)
                m["latest_broken_links"] = broken
                f.seek(0); json.dump(m, f, indent=2); f.truncate()
            logger.info("Injected %d broken links into metrics.json", len(broken))
        except Exception:
            logger.exception("Failed to inject broken links")

    total_min = round((time.time() - start_all) / 60.0, 2)
    logger.info("All done — processed %d locales in %s minutes", len(results), total_min)


if __name__ == "__main__":
    main()