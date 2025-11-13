#!/usr/bin/env bash
# =====================================================================
#  NetRunner — Full Pipeline Runner (v12.2 FINAL)
#  Production-grade • CI-Ready • Safe • Deterministic • Fault-Tolerant
# =====================================================================

set -euo pipefail
IFS=$'\n\t'

# ---------------------------------------------------------------------
#  Flags & Modes
# ---------------------------------------------------------------------
CI_MODE=false
RESET_MODE=false
CLEAR_CACHE_MODE=false
SKIP_LOCALE_UPDATE=false
SKIP_METRICS=false
MAX_PROCS=4   # default, override via cli or env

for arg in "$@"; do
  case "$arg" in
    --ci)                CI_MODE=true ;;
    --reset)             RESET_MODE=true ;;
    --clear-cache)       CLEAR_CACHE_MODE=true ;;
    --skip-locales)      SKIP_LOCALE_UPDATE=true ;;
    --skip-metrics)      SKIP_METRICS=true ;;
    --max-procs=*)       MAX_PROCS="${arg#*=}" ;;
  esac
done

MAX_PROCS="${MAX_PROCS:-4}"

# ---------------------------------------------------------------------
#  Colors (disabled in CI)
# ---------------------------------------------------------------------
if [[ "$CI_MODE" == true ]]; then
  RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
else
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  NC='\033[0m'
fi

log()    { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()     { echo -e "${GREEN}[OK]${NC} $1"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

trap 'error "Unexpected pipeline failure!"' ERR

# ---------------------------------------------------------------------
#  Directories
# ---------------------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DATA_DIR="$ROOT/data"
REPORTS_DIR="$DATA_DIR/reports"
DASH_GEN="$DATA_DIR/dashboard/generated"
LOG_DIR="$ROOT/logs"
VENV="$ROOT/.venv"

mkdir -p "$REPORTS_DIR" "$DASH_GEN" "$LOG_DIR"

# ---------------------------------------------------------------------
#  RESET MODE (DANGER: wipes all outputs)
# ---------------------------------------------------------------------
if [[ "$RESET_MODE" == true ]]; then
  log "Performing FULL RESET (venv + reports + dashboard + logs)…"
  rm -rf "$VENV" "$REPORTS_DIR" "$DASH_GEN" "$LOG_DIR"
  ok "Reset complete."
  exit 0
fi

# ---------------------------------------------------------------------
#  CLEAR-CACHE MODE (safe)
# ---------------------------------------------------------------------
if [[ "$CLEAR_CACHE_MODE" == true ]]; then
  log "Clearing Python caches & temp files…"
  find "$ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find "$ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
  find "$ROOT" -type f -name "*.tmp" -delete 2>/dev/null || true
  ok "Cache cleared."
  exit 0
fi

# ---------------------------------------------------------------------
#  PYTHON CHECK
# ---------------------------------------------------------------------
if ! command -v python3 &>/dev/null; then
  error "Python3 not found. Install Python 3.9+."
  exit 1
fi

PY_VER=$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
log "Python detected: $PY_VER"

# ---------------------------------------------------------------------
#  VIRTUALENV SETUP
# ---------------------------------------------------------------------
if [[ ! -d "$VENV" ]]; then
  log "Creating virtualenv…"
  python3 -m venv "$VENV"
  ok "Virtualenv created."
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

# ---------------------------------------------------------------------
#  INSTALL DEPENDENCIES
# ---------------------------------------------------------------------
log "Installing dependencies…"
pip install --upgrade pip --quiet || warn "Pip upgrade failed."
pip install -r "$ROOT/requirements.txt" --quiet || {
  error "Dependency install failed."
  exit 1
}
ok "Dependencies installed."

# ---------------------------------------------------------------------
#  PRE-RUN CACHE CLEAN
# ---------------------------------------------------------------------
log "Cleaning Python caches…"
find "$ROOT" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" -name "*.pyc" -delete 2>/dev/null || true
ok "Pre-run cleanup complete."

# ---------------------------------------------------------------------
#  LOCALE UPDATE
# ---------------------------------------------------------------------
if [[ "$SKIP_LOCALE_UPDATE" == false ]]; then
  log "Updating locales from live site…"
  if python3 -m src.locales.updater; then
    ok "Locales updated."
  else
    warn "Locale updater failed — using existing locales.json."
  fi
else
  warn "Skipping locale update (--skip-locales)"
fi

# ---------------------------------------------------------------------
#  RUN MAIN PIPELINE
# ---------------------------------------------------------------------
log "Launching NetRunner (max-procs=$MAX_PROCS)…"
MAIN_LOG="$LOG_DIR/main_$(date +"%Y%m%d_%H%M%S").log"

if python3 -m src.main --max-procs="$MAX_PROCS" 2>&1 | tee "$MAIN_LOG"; then
  ok "Main runner completed."
else
  error "Main runner failed — see $MAIN_LOG"
  exit 1
fi

# ---------------------------------------------------------------------
#  METRICS BUILDER
# ---------------------------------------------------------------------
if [[ "$SKIP_METRICS" == false ]]; then
  log "Generating metrics dashboard…"
  MET_LOG="$LOG_DIR/metrics_$(date +"%Y%m%d_%H%M%S").log"
  if python3 -m src.analytics.metrics_builder 2>&1 | tee "$MET_LOG"; then
    ok "Metrics generated."
  else
    error "metrics_builder failed — see $MET_LOG"
  fi
else
  warn "Skipping metrics build (--skip-metrics)"
fi

# ---------------------------------------------------------------------
#  FINAL SAFE CLEANUP
# ---------------------------------------------------------------------
log "Final cleanup…"
find "$ROOT" -name "*.tmp" -delete 2>/dev/null || true
ok "Cleanup done."

echo -e "\n${GREEN}🎯 NetRunner v12.2 pipeline completed successfully.${NC}\n"