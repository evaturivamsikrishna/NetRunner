import os
import shutil
from pathlib import Path

# Define folders to clean
CLEAN_TARGETS = [
    "data/reports",
    "data/dashboard/generated",
    "logs",
]

# Files to skip (like templates, base URLs, or config)
SAFE_KEEP = {
    "data/reports": ["summary_history_Archive.csv"],
    "data/dashboard/generated": ["index.html"],
}

def clean_folder(folder):
    """Safely clear folder contents but skip safe files."""
    path = Path(folder)
    if not path.exists():
        print(f"[INFO] Skipped (not found): {folder}")
        return

    deleted = 0
    for item in path.iterdir():
        if item.is_file():
            if item.name in SAFE_KEEP.get(folder, []):
                print(f"[KEEP] {item}")
                continue
            item.unlink()
            deleted += 1
        elif item.is_dir():
            shutil.rmtree(item)
            deleted += 1
    print(f"[CLEANED] {folder} → {deleted} items removed.")


def reset_project():
    """Main cleaner for reports, dashboard, and logs."""
    print("===============================================")
    print("🧹 Kwalee Monitor Project Reset Utility")
    print("===============================================")

    confirm = input("⚠️  This will delete previous runs, logs, and reports. Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — no files deleted.")
        return

    for folder in CLEAN_TARGETS:
        clean_folder(folder)

    print("\n✅ All previous runs, logs, and analytics cleared!")
    print("➡️  You can now run: bash run.sh to start fresh.\n")


if __name__ == "__main__":
    reset_project()