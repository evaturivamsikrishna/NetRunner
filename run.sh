#!/usr/bin/env bash
# ============================================================
# 🚀 NetRunner — Website Monitor Full Pipeline (v3 CI-Ready)
# ============================================================
# Runs:
#   1. Cleans caches and temp files
#   2. Sets up virtualenv and installs deps
#   3. Runs src.main (Parallel Async Crawler)
#   4. Builds analytics (metrics.json)
#   5. Generates logs, metrics, reports
#
# Usage:
#   ./run.sh             → Full local pipeline
#   ./run.sh --reset     → Clean caches & reports
#   ./run.sh --ci        → Run in CI mode (non-interactive, no color)
# ============================================================

set -euo pipefail
IFS=$'\n\t'

# --- Default Mode ---
CI_MODE=false
RESET_MODE=false

# --- Parse Flags ---
for arg in "$@"; do
  case "$arg" in
    --ci) CI_MODE=true ;;
    --reset) RESET_MODE=true ;;
  esac
done

# --- Auto-detect CI (GitHub Actions / Netlify / Render) ---
if [[ "${CI:-}" == "true" ]]; then
  CI_MODE=true
fi

# --- Color Codes (Disabled in CI) ---
if [[ "$CI_MODE" == true ]]; then
  RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
else
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
fi

print_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
print_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

DATA_DIR="${ROOT_DIR}/data"
REPORTS_DIR="${DATA_DIR}/reports"
DASHBOARD_DIR="${DATA_DIR}/dashboard"
GEN_DIR="${DASHBOARD_DIR}/generated"
LOG_DIR="${ROOT_DIR}/logs"
VENV=".venv"

mkdir -p "$REPORTS_DIR" "$GEN_DIR" "$LOG_DIR"

# ============================================================
# 🧹 RESET MODE
# ============================================================
if [[ "$RESET_MODE" == true ]]; then
  print_info "Performing full cleanup..."
  rm -rf "$VENV" "$REPORTS_DIR" "$GEN_DIR" "$LOG_DIR" __pycache__ .pytest_cache .mypy_cache
  find . -type f -name "*.pyc" -delete 2>/dev/null || true
  print_ok "Project reset complete."
  exit 0
fi

# ============================================================
# 🧼 CLEANUP HELPERS
# ============================================================
clean_pre() {
  print_info "Cleaning caches and logs..."
  find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find . -type f -name "*.pyc" -delete 2>/dev/null || true
  find "$LOG_DIR" -type f -name "*.log" -mtime +7 -delete 2>/dev/null || true
}

clean_post() {
  print_info "Removing temporary files..."
  find . -type f -name "*.tmp" -delete 2>/dev/null || true
}

# ============================================================
# 🧠 ENVIRONMENT SETUP
# ============================================================
check_python() {
  if ! command -v python3 &>/dev/null; then
    print_error "Python 3.8+ is required."
    exit 1
  fi
  PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
  print_info "Python version detected: ${PY_VER}"
}

setup_venv() {
  print_info "Preparing virtualenv..."
  if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    print_ok "Virtualenv created."
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  python -m pip install --upgrade pip >/dev/null 2>&1 || true
}

install_deps() {
  if [[ -f "requirements.txt" ]]; then
    print_info "Installing dependencies..."
    if [[ "$CI_MODE" == true ]]; then
      pip install -r requirements.txt --quiet
    else
      pip install -r requirements.txt >/dev/null 2>&1 || true
    fi
    print_ok "Dependencies ready."
  else
    print_warn "No requirements.txt found — skipping."
  fi
}

# ============================================================
# ⚙️ EXECUTION STAGES
# ============================================================
run_monitor() {
  local TS
  TS=$(date +"%Y%m%d_%H%M%S")
  local LOG_FILE="${LOG_DIR}/monitor_${TS}.log"
  print_info "Running src.main (parallel async crawler)... Log → $LOG_FILE"

  if [[ -f "$VENV/bin/python" ]]; then
    "$VENV/bin/python" -m src.main 2>&1 | tee "$LOG_FILE"
  else
    python3 -m src.main 2>&1 | tee "$LOG_FILE"
  fi
}

run_analytics() {
  local TS
  TS=$(date +"%Y%m%d_%H%M%S")
  local METRIC_LOG="${LOG_DIR}/analytics_${TS}.log"
  print_info "Building metrics.json..."
  
  if [[ -f "$VENV/bin/python" ]]; then
    "$VENV/bin/python" -m src.analytics.metrics_builder 2>&1 | tee "$METRIC_LOG"
  else
    python3 -m src.analytics.metrics_builder 2>&1 | tee "$METRIC_LOG"
  fi
}

# ============================================================
# 🧩 MAIN
# ============================================================
main() {
  echo
  echo "==============================================="
  echo "🚀 NETRUNNER — FULL PIPELINE $( [[ "$CI_MODE" == true ]] && echo "(CI MODE)" )"
  echo "==============================================="
  echo

  clean_pre
  check_python
  setup_venv
  install_deps

  CPU_COUNT=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo "4")
  print_info "Detected ${CPU_COUNT} CPU cores."

  run_monitor || true
  run_analytics || true
  clean_post

  echo
  echo "==============================================="
  echo "✅ PIPELINE COMPLETE"
  echo "-----------------------------------------------"
  echo "📂 Reports:     ${REPORTS_DIR}"
  echo "📊 Metrics:     ${GEN_DIR}/metrics.json"
  echo "🖥 Dashboard:   ${DASHBOARD_DIR}/index.html"
  echo "🪵 Logs:        ${LOG_DIR}"
  echo "==============================================="
  echo
}

# --- Disable fancy output for CI logs ---
if [[ "$CI_MODE" == true ]]; then
  export PYTHONUNBUFFERED=1
  export DISABLE_TQDM=1
  print_info "Running in CI mode — colors & progress bars disabled."
fi

trap 'print_error "⚠️ Script aborted unexpectedly!"' ERR
main "$@"