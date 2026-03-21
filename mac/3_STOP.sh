#!/usr/bin/env bash
# ============================================================
#  TRUTHFORGE AI  |  Stop Application (macOS)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo ""
echo "  ============================================================"
echo "    TRUTHFORGE AI  |  Stopping Application"
echo "  ============================================================"
echo ""

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  if docker-compose ps -q 2>/dev/null | grep -q .; then
    docker-compose down
    echo "  TRUTHFORGE AI stopped successfully."
  else
    echo "  No running Docker containers found."
  fi
else
  echo "  Docker is not running."
  echo "  If you started with Python, press Ctrl+C in the terminal where"
  echo "  streamlit is running, or close that terminal window."
fi

echo ""
