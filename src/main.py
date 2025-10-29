import os
import time
import pandas as pd
import json
import csv
from src.checker import run_checker
from src.analytics.metrics_builder import build_metrics
from src.logger import get_logger

logger = get_logger()

DATA_DIR = "data"
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
DASHBOARD_DIR = os.path.join(DATA_DIR, "dashboard")
METRICS_PATH = os.path.join(DASHBOARD_DIR, "generated", "metrics.json")
LATEST_BROKEN_PATH = os.path.join(REPORTS_DIR, "broken_links_latest.csv")


# ============================================================
# HELPERS
# ============================================================
def find_locale_url_files():
    """Find locale-specific CSVs like urls_to_check_en.csv"""
    locales = []
    for file in os.listdir(DATA_DIR):
        if file.startswith("urls_to_check_") and file.endswith(".csv"):
            locale = file.split("_")[-1].replace(".csv", "")
            locales.append((locale, os.path.join(DATA_DIR, file)))
    return locales


def read_urls(file_path):
    """Read URLs safely from CSV file"""
    try:
        df = pd.read_csv(file_path, header=None)
        urls = [str(u).strip() for u in df[0].tolist() if pd.notna(u)]
        return urls
    except Exception as e:
        logger.error(f"[ERROR] Failed to read URLs from {file_path}: {e}")
        return []


def compute_metrics(total_links, broken_links, unique_links, duration_sec):
    """Compute efficiency and success metrics"""
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
# MAIN EXECUTION
# ============================================================
def main():
    print("\n===============================================")
    print("🚀 Website Monitor - Full Run")
    print("===============================================\n")

    locales = find_locale_url_files()
    if not locales:
        print("[ERROR] No locale URL files found in /data/")
        return

    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(os.path.join(DASHBOARD_DIR, "generated"), exist_ok=True)

    all_invalid_links = []

    for locale, path in locales:
        urls = read_urls(path)
        if not urls:
            print(f"[WARN] No URLs found in {path}")
            continue

        print(f"\n🌍 Running locale: {locale.upper()} ({len(urls)} pages)")
        start = time.time()
        broken_path, invalid_links, all_links, duration = run_checker(urls, output_dir=REPORTS_DIR)
        all_invalid_links.extend(invalid_links)

        metrics = compute_metrics(
            len(all_links), len(invalid_links), len({l['url'] for l in all_links}), duration
        )

        summary = {
            "run_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "locale": locale,
            "pages_checked": len(urls),
            "total_links_found": len(all_links),
            "unique_links": len({l['url'] for l in all_links}),
            "duplicate_count": metrics["duplicate_count"],
            "crawler_efficiency": metrics["crawler_efficiency"],
            "broken_links": len(invalid_links),
            "duration_sec": round(duration, 2),
            "duration_mins": metrics["duration_mins"],
            "success_rate": metrics["success_rate"],
            "status": "✅ Healthy" if len(invalid_links) == 0 else f"⚠️ {len(invalid_links)} broken",
        }

        summary_path = os.path.join(REPORTS_DIR, f"summary_history_{locale}.csv")
        df = pd.DataFrame([summary])
        df.to_csv(summary_path, mode="a", header=not os.path.exists(summary_path), index=False)
        print(f"[📈] Summary updated → {summary_path}")

    print("\n[INFO] Running analytics generator...")
    metrics = build_metrics()

    # ============================================================
    # 🔄 Inject latest broken links into metrics.json
    # ============================================================
    try:
        if os.path.exists(LATEST_BROKEN_PATH):
            with open(LATEST_BROKEN_PATH, encoding="utf-8") as f:
                broken_data = list(csv.DictReader(f))

            # load metrics.json if available
            if os.path.exists(METRICS_PATH):
                with open(METRICS_PATH, "r+", encoding="utf-8") as f:
                    data = json.load(f)
                    data["latest_broken_links"] = broken_data
                    f.seek(0)
                    json.dump(data, f, indent=2)
                    f.truncate()
                print(f"🔗 Injected {len(broken_data)} latest broken links into metrics.json")
    except Exception as e:
        logger.error(f"[ERROR] Failed to update metrics.json with broken links: {e}")

    print("\n✅ Dashboard metrics successfully generated.")
    print("📊 Dashboard: data/dashboard/index.html")
    print("📈 Metrics: data/dashboard/generated/metrics.json")
    print("🗂 Reports: data/reports/")


if __name__ == "__main__":
    main()