import csv
import pandas as pd
import os

# ============================================================
# 🧠 UNIVERSAL CSV SCHEMA NORMALIZER
# ============================================================

def reconcile_csv_schema(csv_path: str):
    """
    Ensures that a given CSV file has all the expected columns.
    Adds missing columns with blank (0 or empty string) values,
    and reorders them into a standard schema for analytics.
    
    Compatible with:
      - summary_history.csv (global)
      - summary_history_<locale>.csv
      - summary_latest.csv (if exists)
    """

    if not os.path.exists(csv_path):
        print(f"[WARN] {csv_path} does not exist — skipping schema reconciliation.")
        return

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
    except Exception as e:
        print(f"[WARN] Could not read headers from {csv_path}: {e}")
        return

    # --- Define your canonical column order ---
    expected_columns = [
        "run_time",
        "pages_checked",
        "total_links_found",
        "unique_links",
        "duplicate_count",
        "crawler_efficiency",
        "broken_links",
        "duration_sec",
        "duration_mins",
        "status"
    ]

    # Detect missing columns
    missing_cols = [c for c in expected_columns if c not in headers]
    extra_cols = [c for c in headers if c not in expected_columns]

    if not missing_cols and not extra_cols:
        # Already perfect
        return

    print(f"[INFO] Reconciling schema for {csv_path}")
    print(f"  → Missing columns: {missing_cols}" if missing_cols else f"  → No missing columns.")
    if extra_cols:
        print(f"  → Extra columns: {extra_cols} (kept for safety)")

    try:
        df = pd.read_csv(csv_path, encoding="utf-8")

        # Add missing columns with default values
        for col in missing_cols:
            df[col] = 0 if col.startswith(("duration_", "total_", "broken_", "crawler_")) else ""

        # Merge existing + expected + extra (if any)
        all_cols = expected_columns + [c for c in df.columns if c not in expected_columns]

        # Reorder columns (keeping new/extra at end)
        df = df[[c for c in all_cols if c in df.columns]]

        # Overwrite the fixed CSV
        df.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"[SUCCESS] {csv_path} schema normalized ({len(df.columns)} columns).")

    except Exception as e:
        print(f"[ERROR] Failed to reconcile schema for {csv_path}: {e}")