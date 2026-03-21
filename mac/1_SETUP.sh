#!/usr/bin/env bash
# ============================================================
#  TRUTHFORGE AI  |  First-Time Setup (macOS)
#  Double-click in Finder, or run:  bash mac/1_SETUP.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."   # always run from project root

echo ""
echo "  ============================================================"
echo "    TRUTHFORGE AI  |  First-Time Setup  (macOS)"
echo "  ============================================================"
echo ""

# ── Helper ───────────────────────────────────────────────────────────────────
die() { echo ""; echo "  [ERROR] $*"; echo ""; exit 1; }

# ── Detect preferred install path ────────────────────────────────────────────
echo "  Which installation method would you like?"
echo ""
echo "    [1] Docker  (recommended — easiest, cleanest)"
echo "    [2] Native Python  (no Docker required)"
echo ""
read -rp "  Enter 1 or 2: " CHOICE

case "$CHOICE" in
  1) INSTALL_DOCKER=true ;;
  2) INSTALL_DOCKER=false ;;
  *) die "Invalid choice. Re-run and enter 1 or 2." ;;
esac

echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  OPTION A — Docker
# ══════════════════════════════════════════════════════════════════════════════
if [ "$INSTALL_DOCKER" = true ]; then

  echo "  [1/3] Checking for Docker..."
  if ! command -v docker &>/dev/null; then
    echo ""
    echo "  [!] Docker is NOT installed."
    echo "  Please download Docker Desktop for Mac from:"
    echo "  https://www.docker.com/products/docker-desktop/"
    echo ""
    open "https://www.docker.com/products/docker-desktop/" 2>/dev/null || true
    echo "  After installing and starting Docker Desktop, re-run this script."
    echo ""
    exit 1
  fi
  docker --version
  echo "  Docker found. OK."
  echo ""

  echo "  [2/3] Checking Docker daemon..."
  if ! docker info &>/dev/null; then
    echo ""
    echo "  [!] Docker Desktop is installed but not running."
    echo "  Please open Docker Desktop from your Applications folder, wait for"
    echo "  the whale icon to appear in the menu bar, then re-run this script."
    echo ""
    exit 1
  fi
  echo "  Docker daemon is running. OK."
  echo ""

  echo "  [3/3] Setting up API keys..."
  if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "  Created .env from template."
    echo ""
    echo "  ============================================================"
    echo "   IMPORTANT: Add your API key to .env before continuing!"
    echo "   Opening the file in TextEdit now..."
    echo "  ============================================================"
    echo ""
    open -a TextEdit ".env" 2>/dev/null || nano ".env"
    echo ""
    read -rp "  Press ENTER after you have saved your API key... " _
  else
    echo "  .env file already exists. OK."
  fi
  echo ""

  echo "  Building TRUTHFORGE Docker image..."
  echo "  (This may take 5-10 minutes on first run)"
  echo ""
  docker-compose build --no-cache
  echo ""
  echo "  ============================================================"
  echo "   Setup complete!"
  echo "   Run  bash mac/2_START.sh  (or double-click it) to launch."
  echo "  ============================================================"
  echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  OPTION B — Native Python
# ══════════════════════════════════════════════════════════════════════════════
else

  echo "  [1/5] Checking Python version..."
  if ! command -v python3 &>/dev/null; then
    echo ""
    echo "  [!] Python 3 is NOT installed."
    echo "  Please install Python 3.11+ from:"
    echo "  https://www.python.org/downloads/"
    open "https://www.python.org/downloads/" 2>/dev/null || true
    exit 1
  fi

  PYVER=$(python3 --version 2>&1 | awk '{print $2}')
  PY_MINOR=$(echo "$PYVER" | cut -d. -f2)
  echo "  Python $PYVER found."
  if [ "$PY_MINOR" -lt 11 ]; then
    die "Python 3.11+ required. Found $PYVER. Download: https://www.python.org/downloads/"
  fi
  echo ""

  echo "  [2/5] Creating virtual environment..."
  if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  Virtual environment created."
  else
    echo "  Virtual environment already exists."
  fi
  echo ""

  echo "  [3/5] Installing dependencies (this may take 5-10 minutes)..."
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip --quiet
  pip install -r requirements.txt
  echo "  Dependencies installed."
  echo ""

  echo "  [4/5] Downloading spaCy language model..."
  python3 -m spacy download en_core_web_sm
  echo "  Language model downloaded."
  echo ""

  echo "  [5/5] Setting up API keys..."
  if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "  Created .env from template."
    echo ""
    echo "  ============================================================"
    echo "   IMPORTANT: Add your API key to .env before continuing!"
    echo "  ============================================================"
    echo ""
    open -a TextEdit ".env" 2>/dev/null || nano ".env"
    echo ""
    read -rp "  Press ENTER after saving your API key... " _
  else
    echo "  .env file already exists. OK."
  fi
  echo ""

  echo "  ============================================================"
  echo "   Setup complete!"
  echo "   Run  bash mac/2_START.sh  (or double-click it) to launch."
  echo "  ============================================================"
  echo ""

fi
