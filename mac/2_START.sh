#!/usr/bin/env bash
# ============================================================
#  TRUTHFORGE AI  |  Start Application (macOS)
#  Double-click in Finder, or run:  bash mac/2_START.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."   # always run from project root

echo ""
echo "  ============================================================"
echo "    TRUTHFORGE AI  |  Starting Application"
echo "  ============================================================"
echo ""

die() { echo ""; echo "  [ERROR] $*"; echo ""; exit 1; }

# ── Check .env ────────────────────────────────────────────────────────────────
[ -f ".env" ] || die ".env file not found. Run mac/1_SETUP.sh first."

# ── Decide: Docker or Python? ─────────────────────────────────────────────────
if [ -d "venv" ]; then
  USE_DOCKER=false
elif command -v docker &>/dev/null && docker info &>/dev/null; then
  USE_DOCKER=true
else
  die "Neither Docker nor a Python venv found. Run mac/1_SETUP.sh first."
fi

# ══════════════════════════════════════════════════════════════════════════════
if [ "$USE_DOCKER" = true ]; then

  echo "  Starting via Docker..."

  # Build image if not present
  if ! docker image inspect truthforge:latest &>/dev/null; then
    echo "  [!] Docker image not found — building now..."
    docker-compose build || die "Build failed. Run mac/1_SETUP.sh first."
  fi

  docker-compose up -d || die "Failed to start Docker containers."

  echo ""
  echo "  Waiting for app to be ready..."
  ATTEMPTS=0
  until curl -sf http://localhost:8501/_stcore/health &>/dev/null; do
    ATTEMPTS=$((ATTEMPTS + 1))
    [ $ATTEMPTS -ge 12 ] && { echo "  Timed out — try opening http://localhost:8501 manually."; break; }
    echo "  Still starting... ($ATTEMPTS/12)"
    sleep 5
  done

  echo ""
  echo "  ============================================================"
  echo "   TRUTHFORGE AI is running!"
  echo "   Opening http://localhost:8501 in your browser..."
  echo "  ============================================================"
  echo ""
  open "http://localhost:8501"
  echo "  To stop the app, run:  bash mac/3_STOP.sh"
  echo ""

# ══════════════════════════════════════════════════════════════════════════════
else

  echo "  Starting via native Python..."

  # shellcheck disable=SC1091
  source venv/bin/activate

  echo "  TRUTHFORGE AI is starting on http://localhost:8501"
  echo "  Press Ctrl+C in this terminal to stop."
  echo ""

  # Open browser after a short delay
  (sleep 3 && open "http://localhost:8501") &

  streamlit run main.py \
    --server.port=8501 \
    --server.headless=true \
    --browser.gatherUsageStats=false

fi
