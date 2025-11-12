# src/main.py
import os
import time
import json
import csv
import requests
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from src.analytics.metrics_builder import build_metrics
from src.logger import get_logger
from src.checker import run_checker
from src.constants.locales import LOCALES

# ============================================================
# CONFIG
# ============================================================
logger = get_logger()
DATA_DIR = "data"
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
DASHBOARD_DIR = os.path.join(DATA_DIR, "dashboard")
GENERATED_DIR = os.path.join(DASHBOARD_DIR, "generated")
METRICS_PATH = os.path.join(GENERATED_DIR, "metrics.json")
LATEST_BROKEN_PATH = os.path.join(REPORTS_DIR, "broken_links_latest.csv")

BASE_URL = "https://kwalee.com"     # ← change to your domain root if needed
MAX_PROCESSES = 4                   # concurrent locales (multiprocessing)

# NOTE: If run_checker uses asyncio or non-picklable state, ensure it is importable
# ============================================================
# HELPERS
# ============================================================


def find_locale_url_files():
    """
    Find locale-specific CSVs like urls_to_check_en.csv in /data
    returns list of tuples: (locale_key, full_path)
    """
    locales = []
    if not os.path.isdir(DATA_DIR):
        return locales
    for file in os.listdir(DATA_DIR):
        if file.startswith("urls_to_check_") and file.endswith(".csv"):
            locale = file.replace("urls_to_check_", "").replace(".csv", "")
            locales.append((locale, os.path.join(DATA_DIR, file)))
    return locales


def read_urls(file_path):
    """Read URLs safely from CSV file (one URL per line)"""
    try:
        df = pd.read_csv(file_path, header=None)
        return [str(u).strip() for u in df[0].tolist() if pd.notna(u)]
    except Exception as e:
        get_logger().error(f"[ERROR] Failed to read URLs from {file_path}: {e}")
        return []


def resolve_locale_path(locale_key: str) -> str:
    """
    Map short locale key -> site path segment.
    Examples:
      en -> "/"     (empty mapping means base site)
      es -> "/es-es/"
      ptbr -> "/pt-br/"
    """
    mapped = LOCALES.get(locale_key, locale_key)
    if not mapped:
        return "/"
    # ensure leading and trailing slash
    return "/" + mapped.strip("/ ") + "/"


def check_locale_homepage(locale_key: str, timeout=10):
    """
    Ping locale homepage before running. Returns True if live (200/301/302).
    Tries:
      1) root mapped path (resolve_locale_path)
      2) fallback to base URL root (only if mapped path failed)
    """
    url_path = resolve_locale_path(locale_key)
    url = BASE_URL.rstrip("/") + url_path
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        code = resp.status_code
        if code in (200, 301, 302):
            return True, url, code
        # attempt lightweight GET for sites that block HEAD
        resp2 = requests.get(url, timeout=timeout, allow_redirects=True)
        if resp2.status_code in (200, 301, 302):
            return True, url, resp2.status_code
        # fallback: try base root (only if not root already)
        if url_path != "/":
            resp_root = requests.head(BASE_URL, timeout=timeout, allow_redirects=True)
            if resp_root.status_code in (200, 301, 302):
                return False, url, code  # locale path missing but root up
        return False, url, code
    except requests.RequestException as e:
        return False, url, str(e)


def compute_metrics(total_links, broken_links, unique_links, duration_sec):
    """Compute crawler metrics"""
    success_rate = 100 - ((broken_links / total_links) * 100 if total_links else 0)
    duplicate_count = total_links - unique_links
    efficiency = (unique_links / total_links * 100) if total_links else 0
    return {
        "success_rate": round(success_rate, 2),
        "duplicate_count": duplicate_count,
        "crawler_efficiency": round(efficiency, 2),
        "duration_mins": round(duration_sec / 60, 2),
    }


# ============================================================
# WORKER (runs inside child process)
# ============================================================
def process_locale(locale, path):
    """
    Run a locale in isolation (safe for multiprocessing).
    Returns: (locale_key, summary_dict)
    """
    # create local logger in worker to avoid multiprocessing issues
    sub_logger = get_logger(f"worker-{locale}")

    # ensure reports directory exists in worker
    os.makedirs(REPORTS_DIR, exist_ok=True)

    urls = read_urls(path)
    if not urls:
        sub_logger.warning(f"[WARN] No URLs found for {locale}")
        return locale, {"status": "Skipped (No URLs)", "pages_checked": 0}

    # Check homepage availability using resolved path
    live, checked_url, code_or_err = check_locale_homepage(locale)
    if not live:
        sub_logger.warning(f"⏭️ Skipping locale '{locale}' — homepage not available: {checked_url} ({code_or_err})")
        return locale, {"status": "Skipped (homepage unavailable)", "pages_checked": 0, "checked_url": checked_url, "reason": str(code_or_err)}

    sub_logger.info(f"🌍 Starting locale: {locale.upper()} — {len(urls)} pages (homepage OK: {checked_url})")
    start = time.time()

    try:
        # run_checker should return: (broken_path, invalid_links, all_links, duration)
        broken_path, invalid_links, all_links, duration = run_checker(urls, output_dir=REPORTS_DIR)
    except Exception as e:
        sub_logger.exception(f"❌ run_checker failed for {locale}: {e}")
        return locale, {"status": "Failed (checker error)", "pages_checked": len(urls), "error": str(e)}

    unique_links = len({l.get("url") for l in all_links if l.get("url")})
    metrics = compute_metrics(len(all_links), len(invalid_links), unique_links, duration)

    summary = {
        "run_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "locale": locale,
        "pages_checked": len(urls),
        "total_links_found": len(all_links),
        "unique_links": unique_links,
        "duplicate_count": metrics["duplicate_count"],
        "crawler_efficiency": metrics["crawler_efficiency"],
        "broken_links": len(invalid_links),
        "duration_sec": round(duration, 2),
        "duration_mins": metrics["duration_mins"],
        "success_rate": metrics["success_rate"],
        "status": "✅ Healthy" if len(invalid_links) == 0 else f"⚠️ {len(invalid_links)} broken",
    }

    # Append summary CSV (worker safe append)
    try:
        summary_path = os.path.join(REPORTS_DIR, f"summary_history_{locale}.csv")
        df = pd.DataFrame([summary])
        df.to_csv(summary_path, mode="a", header=not os.path.exists(summary_path), index=False)
        sub_logger.info(f"[📈] Summary updated → {summary_path}")
    except Exception as e:
        sub_logger.warning(f"[WARN] Could not write summary CSV for {locale}: {e}")

    sub_logger.info(f"✅ {locale.upper()} done — {summary['duration_mins']} mins, {summary['broken_links']} broken")
    return locale, summary


# ============================================================
# MAIN
# ============================================================
def main():
    print("\n===============================================")
    print("🚀 Website Monitor — Parallel Run Mode")
    print("===============================================\n")

    locales = find_locale_url_files()
    if not locales:
        logger.error("❌ No locale CSVs found under /data/")
        return

    # ensure directories exist BEFORE launching workers (prevents races)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(GENERATED_DIR, exist_ok=True)

    start_all = time.time()
    results = {}
    failed = []

    # Start multiprocessing pool
    with ProcessPoolExecutor(max_workers=MAX_PROCESSES) as executor:
        futures = {executor.submit(process_locale, loc, path): loc for loc, path in locales}
        for future in as_completed(futures):
            loc = futures[future]
            try:
                _, summary = future.result()
                results[loc] = summary
                logger.info(f"✅ {loc.upper()} completed — {summary.get('status')}")
            except Exception as e:
                logger.exception(f"❌ {loc.upper()} failed during processing: {e}")
                failed.append(loc)

    # Run analytics generator (single process)
    try:
        logger.info("[INFO] Running analytics generator (build_metrics)...")
        build_metrics()
    except Exception as e:
        logger.exception(f"[ERROR] build_metrics failed: {e}")

    # Write combined metrics file
    try:
        metrics_obj = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "locales": results,
        }
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics_obj, f, indent=2)
        logger.info(f"📈 Metrics written → {METRICS_PATH}")
    except Exception as e:
        logger.exception(f"[ERROR] Failed to write metrics.json: {e}")

    # Optionally inject latest broken links CSV into metrics
    if os.path.exists(LATEST_BROKEN_PATH):
        try:
            with open(LATEST_BROKEN_PATH, encoding="utf-8") as f:
                broken_data = list(csv.DictReader(f))
            with open(METRICS_PATH, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["latest_broken_links"] = broken_data
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
            logger.info(f"🔗 Injected {len(broken_data)} broken links → metrics.json")
        except Exception as e:
            logger.exception(f"[ERROR] Failed to inject broken links into metrics.json: {e}")

    total_mins = round((time.time() - start_all) / 60, 2)
    print("\n✅ Dashboard metrics successfully generated.")
    print(f"📊 Dashboard: {DASHBOARD_DIR}/index.html")
    print(f"📈 Metrics: {METRICS_PATH}")
    print(f"🗂 Reports: {REPORTS_DIR}")
    print(f"⏱ Total time: {total_mins} min")


if __name__ == "__main__":
    main()