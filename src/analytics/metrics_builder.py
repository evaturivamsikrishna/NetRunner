import os
import json
import pandas as pd
from datetime import datetime, timedelta
from glob import glob
from src.utils.Summary_fixed import reconcile_csv_schema

REPORTS_DIR = "data/reports"
OUTPUT_DIR = "data/dashboard/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)
METRICS_PATH = os.path.join(OUTPUT_DIR, "metrics.json")

def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def safe_int(value):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0

def load_locale_data():
    csv_files = glob(os.path.join(REPORTS_DIR, "summary_history_*.csv"))
    locale_data = {}
    for file in csv_files:
        locale = os.path.basename(file).replace("summary_history_", "").replace(".csv", "")
        try:
            reconcile_csv_schema(file)
            df = pd.read_csv(file)
            if df.empty:
                continue
            for col in [
                "total_links_found", "unique_links", "duplicate_count",
                "broken_links", "duration_sec", "crawler_efficiency"
            ]:
                if col in df.columns:
                    df[col] = df[col].apply(safe_float)
            for col in [
                "localized_rescues", "canonical_matches",
                "js_recoveries", "false_positive_avoided"
            ]:
                if col not in df.columns:
                    df[col] = 0
            df["locale"] = locale
            locale_data[locale] = df
        except Exception as e:
            print(f"[WARN] Failed to load {file}: {e}")
    return locale_data

def build_metrics():
    locale_data = load_locale_data()
    if not locale_data:
        print("[ERROR] No locale summary files found.")
        return None

    combined = pd.concat(locale_data.values(), ignore_index=True)
    combined["run_time"] = pd.to_datetime(combined["run_time"], errors="coerce")
    combined = combined.dropna(subset=["run_time"])

    total_runs = len(combined)
    runs_today = len(combined[combined["run_time"].dt.date == datetime.utcnow().date()])
    total_links = safe_int(combined["total_links_found"].sum())
    total_broken = safe_int(combined["broken_links"].sum())

    # --- Compute error type breakdown ---
    error_breakdown = {}
    if "status_code" in combined.columns:
        codes = combined["status_code"].fillna(0).astype(int)
        error_breakdown = {
            "404 Not Found": int((codes == 404).sum()),
            "500+ Server Errors": int(((codes >= 500) & (codes < 600)).sum()),
            "410 Gone": int((codes == 410).sum()),
            "Soft 404s": int((combined["status"].astype(str).str.contains("SOFT", case=False)).sum()),
            "403 / Cloudflare": int((codes == 403).sum())
        }

    global_metrics = {
        "total_runs": total_runs,
        "runs_today": runs_today,
        "total_links_checked": total_links,
        "total_broken_links": total_broken,
        "average_duration_sec": round(combined["duration_sec"].mean(), 2),
        "average_efficiency": round(combined["crawler_efficiency"].mean(), 2),
        "overall_success_rate": round(100 - (total_broken / max(total_links, 1) * 100), 2),
        "localized_rescues": safe_int(combined["localized_rescues"].sum()),
        "canonical_matches": safe_int(combined["canonical_matches"].sum()),
        "js_recoveries": safe_int(combined["js_recoveries"].sum()),
        "false_positive_avoided": safe_int(combined["false_positive_avoided"].sum()),
    }

    locale_summaries = {}
    for locale, df in locale_data.items():
        latest = df.iloc[-1]
        locale_summaries[locale] = {
            "latest_run": str(latest.get("run_time")),
            "total_runs": len(df),
            "total_links": safe_int(df["total_links_found"].sum()),
            "avg_success_rate": round(100 - (df["broken_links"].sum() / max(df["total_links_found"].sum(), 1) * 100), 2),
            "avg_efficiency": round(df["crawler_efficiency"].mean(), 2),
            "avg_duration_mins": round(df["duration_sec"].mean() / 60, 2),
            "localized_rescues": safe_int(df["localized_rescues"].sum()),
            "canonical_matches": safe_int(df["canonical_matches"].sum()),
            "js_recoveries": safe_int(df["js_recoveries"].sum()),
        }

    cutoff_date = (datetime.utcnow() - timedelta(days=7)).date()
    df_recent = combined[combined["run_time"].dt.date >= cutoff_date]
    weekly_trend = (
        df_recent.groupby(df_recent["run_time"].dt.date)
        .agg({
            "broken_links": "sum",
            "total_links_found": "sum",
            "crawler_efficiency": "mean",
            "localized_rescues": "sum",
            "canonical_matches": "sum"
        })
        .reset_index()
        .rename(columns={"run_time": "date"})
    )
    weekly_trend["success_rate"] = round(
        100 - (weekly_trend["broken_links"] / weekly_trend["total_links_found"] * 100), 2
    )
    weekly_trend["date"] = weekly_trend["date"].astype(str)

    latest_run = combined.iloc[-1]
    latest_summary = {
        "time": str(latest_run.get("run_time")),
        "broken_links": safe_int(latest_run.get("broken_links")),
        "total_links": safe_int(latest_run.get("total_links_found")),
        "duration_sec": safe_float(latest_run.get("duration_sec")),
        "success_rate": round(100 - (latest_run.get("broken_links", 0) / max(latest_run.get("total_links_found", 1), 1) * 100), 2),
        "localized_rescues": safe_int(latest_run.get("localized_rescues")),
        "canonical_matches": safe_int(latest_run.get("canonical_matches")),
        "js_recoveries": safe_int(latest_run.get("js_recoveries")),
    }

    metrics = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "global": global_metrics,
        "locales": locale_summaries,
        "latest_run": latest_summary,
        "weekly_trend": weekly_trend.to_dict(orient="records"),
        "error_breakdown": error_breakdown,
    }

    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(f"✅ Metrics successfully generated → {METRICS_PATH}")
    return metrics

if __name__ == "__main__":
    build_metrics()