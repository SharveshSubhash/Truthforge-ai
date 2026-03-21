#!/usr/bin/env bash
# ============================================================
# package_windows.sh
# Creates a distributable ZIP for Windows users.
# Run from the truthforge project root:   bash package_windows.sh
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_NAME="TRUTHFORGE_AI_Windows"
DIST_DIR="/tmp/${DIST_NAME}"
OUTPUT_ZIP="${PROJECT_ROOT}/${DIST_NAME}.zip"

echo ""
echo "  ============================================================"
echo "    TRUTHFORGE AI  |  Windows Distribution Packager"
echo "  ============================================================"
echo ""

# ── Clean up previous build ──────────────────────────────────────────────────
rm -rf "${DIST_DIR}" "${OUTPUT_ZIP}"
mkdir -p "${DIST_DIR}"

# ── Copy source files (exclude secrets, cache, git) ─────────────────────────
echo "  [1/3] Copying project files..."

rsync -a \
  --exclude='.env' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='venv' \
  --exclude='.venv' \
  --exclude='reports/*' \
  --exclude='*.tar.gz' \
  --exclude='*.zip' \
  --exclude='*.egg-info' \
  --exclude='htmlcov' \
  --exclude='.DS_Store' \
  --exclude='*.log' \
  --exclude="${DIST_NAME}.zip" \
  "${PROJECT_ROOT}/" "${DIST_DIR}/"

# ── Ensure reports folder exists (for Docker volume mount) ───────────────────
mkdir -p "${DIST_DIR}/reports"
touch    "${DIST_DIR}/reports/.gitkeep"

# ── Copy Windows scripts to root of the zip ──────────────────────────────────
echo "  [2/3] Preparing launcher scripts..."
cp "${DIST_DIR}/windows/1_SETUP.bat"        "${DIST_DIR}/1_SETUP.bat"
cp "${DIST_DIR}/windows/2_START.bat"        "${DIST_DIR}/2_START.bat"
cp "${DIST_DIR}/windows/3_STOP.bat"         "${DIST_DIR}/3_STOP.bat"
cp "${DIST_DIR}/windows/SETUP_PYTHON.bat"   "${DIST_DIR}/SETUP_PYTHON.bat"
cp "${DIST_DIR}/windows/START_PYTHON.bat"   "${DIST_DIR}/START_PYTHON.bat"
cp "${DIST_DIR}/windows/README_WINDOWS.txt" "${DIST_DIR}/README_WINDOWS.txt"

# ── Create the ZIP ───────────────────────────────────────────────────────────
echo "  [3/3] Creating ZIP archive..."
cd /tmp
zip -r "${OUTPUT_ZIP}" "${DIST_NAME}" -x "*.DS_Store"

# ── Summary ──────────────────────────────────────────────────────────────────
ZIP_SIZE=$(du -sh "${OUTPUT_ZIP}" | cut -f1)
echo ""
echo "  ============================================================"
echo "   Done!"
echo "   Output: ${OUTPUT_ZIP}"
echo "   Size:   ${ZIP_SIZE}"
echo ""
echo "   Share ${DIST_NAME}.zip with your friend."
echo "   They should read README_WINDOWS.txt first."
echo "  ============================================================"
echo ""
