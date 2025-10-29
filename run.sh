#!/usr/bin/env bash
# ============================================================
# 🚀 Website Monitor - Full Automated Pipeline (Final Version)
# ------------------------------------------------------------
# Runs the complete workflow:
#   1. Cleans caches
#   2. Ensures Python + virtualenv setup
#   3. Runs src.main (Async Monitor)
#   4. Generates analytics (metrics.json)
#   5. Keeps logs, reports, dashboard data
#
# Compatible with:
#   - Local CLI runs
#   - CI (GitHub Actions / Netlify / Render)
# ============================================================

set -u

# --- Color Codes ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status()   { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success()  { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning()  { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error()    { echo -e "${RED}[ERROR]${NC} $1"; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

# ============================================================
# USAGE:
#   ./run.sh           → full pipeline
#   ./run.sh --reset   → full cleanup (calls src.utils.reset_project)
# ============================================================

# ------------------------------------------------------------
# OPTIONAL RESET MODE
# ------------------------------------------------------------
if [[ "${1:-}" == "--reset" ]]; then
  print_status "🧹 Performing full project reset..."
  if [[ -f ".venv/bin/python" ]]; then
    .venv/bin/python -m src.utils.reset_project || true
  else
    python3 -m src.utils.reset_project || true
  fi
  print_success "✅ Reset complete."
  exit 0
fi

# ============================================================
# PRE-RUN CLEANUP
# ============================================================
clean_pre() {
  print_status "Cleaning Python caches..."
  find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  rm -rf ~/.cache/pip 2>/dev/null || true
  print_success "Pre-run cleanup complete."
}

clean_post() {
  print_status "Removing temporary files..."
  find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  print_success "Post-run cleanup done."
}

# ============================================================
# PYTHON + ENVIRONMENT SETUP
# ============================================================
check_python() {
  print_status "Checking for python3..."
  if ! command -v python3 &>/dev/null; then
    print_error "Python 3.8+ is required but not installed."
    exit 1
  fi
  PY_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
  print_status "Detected Python version: ${PY_VER}"
}

setup_venv() {
  print_status "Setting up virtual environment (.venv)..."
  if [[ -d ".venv" ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    print_status "Using existing .venv environment."
  else
    python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install --upgrade pip >/dev/null 2>&1 || true
    print_success ".venv created successfully."
  fi
}

install_deps() {
  if [[ -f "requirements.txt" ]]; then
    print_status "Installing Python dependencies..."
    python -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
    python -m pip install -r requirements.txt >/dev/null 2>&1 || true
    print_success "Dependencies installed successfully."
  else
    print_warning "No requirements.txt found — skipping dependency install."
  fi
}

# ============================================================
# PATH SETUP
# ============================================================
DATA_DIR="${ROOT_DIR}/data"
REPORTS_DIR="${DATA_DIR}/reports"
DASHBOARD_DIR="${DATA_DIR}/dashboard"
GEN_DIR="${DASHBOARD_DIR}/generated"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "$REPORTS_DIR" "$GEN_DIR" "$LOG_DIR"

# ============================================================
# RUNNER FUNCTIONS
# ============================================================
run_monitor() {
  TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
  LOG_FILE="${LOG_DIR}/run_${TIMESTAMP}.log"
  print_status "Running async monitor (src.main)... Logging → ${LOG_FILE}"

  if [[ -f ".venv/bin/python" ]]; then
    .venv/bin/python -m src.main 2>&1 | tee -a "$LOG_FILE"
    STATUS=${PIPESTATUS[0]:-0}
  else
    python3 -m src.main 2>&1 | tee -a "$LOG_FILE"
    STATUS=${PIPESTATUS[0]:-0}
  fi

  if [[ $STATUS -ne 0 ]]; then
    print_warning "Monitor exited with code $STATUS. Continuing..."
  else
    print_success "Monitor completed successfully."
  fi
  return $STATUS
}

run_analytics() {
  METRIC_LOG="${LOG_DIR}/metrics_$(date +"%Y%m%d_%H%M%S").log"
  print_status "Running analytics generator (metrics_builder)..."
  
  if [[ -f ".venv/bin/python" ]]; then
    .venv/bin/python -m src.analytics.metrics_builder 2>&1 | tee -a "$METRIC_LOG"
    METRIC_STATUS=${PIPESTATUS[0]:-0}
  else
    python3 -m src.analytics.metrics_builder 2>&1 | tee -a "$METRIC_LOG"
    METRIC_STATUS=${PIPESTATUS[0]:-0}
  fi

  if [[ $METRIC_STATUS -ne 0 ]]; then
    print_warning "Analytics encountered issues. Check logs."
  else
    print_success "Analytics completed successfully (metrics.json updated)."
  fi
}

# ============================================================
# MAIN EXECUTION
# ============================================================
main() {
  echo
  echo "==============================================="
  echo "🚀 WEBSITE MONITOR - FULL PIPELINE START"
  echo "==============================================="
  echo

  clean_pre
  check_python
  setup_venv
  install_deps

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

main "$@"