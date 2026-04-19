#!/usr/bin/env bash
# ============================================================
#  package_all.sh
#  Creates a cross-platform ZIP for both macOS and Windows.
#  Run from the truthforge project root:   bash package_all.sh
# ============================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="v1.1"
DIST_NAME="TRUTHFORGE_AI_${VERSION}"
DIST_DIR="/tmp/${DIST_NAME}"
OUTPUT_ZIP="${PROJECT_ROOT}/${DIST_NAME}.zip"

echo ""
echo "  ============================================================"
echo "    TRUTHFORGE AI  |  Cross-Platform Packager  (${VERSION})"
echo "  ============================================================"
echo ""

# ── Safety check — confirm .env is excluded ───────────────────────────────────
if [ -f "${PROJECT_ROOT}/.env" ]; then
  echo "  [✓] .env found in project root — will be EXCLUDED from zip."
else
  echo "  [i] No .env file present (nothing to exclude)."
fi
echo ""

# ── Clean up previous build ───────────────────────────────────────────────────
rm -rf "${DIST_DIR}" "${OUTPUT_ZIP}"
mkdir -p "${DIST_DIR}"

# ── Copy source files ─────────────────────────────────────────────────────────
echo "  [1/5] Copying project files..."

rsync -a \
  --exclude='.env' \
  --exclude='.git' \
  --exclude='.gitignore' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.pytest_cache' \
  --exclude='venv' \
  --exclude='.venv' \
  --exclude='reports/*' \
  --exclude='artifacts/runs/*' \
  --exclude='logs/*' \
  --exclude='memory_store/*' \
  --exclude='*.tar.gz' \
  --exclude='*.zip' \
  --exclude='*.egg-info' \
  --exclude='htmlcov' \
  --exclude='.DS_Store' \
  --exclude='*.log' \
  --exclude='judgments_test/' \
  --exclude='Test*/' \
  --exclude='memory/*.json' \
  --exclude='docs/create_changelog.js' \
  "${PROJECT_ROOT}/" "${DIST_DIR}/"

echo "  Files copied (secrets excluded)."

# ── Verify .env was NOT included ─────────────────────────────────────────────
if [ -f "${DIST_DIR}/.env" ]; then
  echo ""
  echo "  [!!!] SECURITY ALERT: .env was copied — removing it now!"
  rm -f "${DIST_DIR}/.env"
fi

# ── Ensure placeholder directories exist ─────────────────────────────────────
echo ""
echo "  [2/5] Creating placeholder directories..."
for DIR in reports artifacts/runs logs memory_store; do
  mkdir -p "${DIST_DIR}/${DIR}"
  touch    "${DIST_DIR}/${DIR}/.gitkeep"
done

# ── Windows: copy batch files to project root ─────────────────────────────────
echo ""
echo "  [3/5] Preparing Windows launchers..."
cp "${DIST_DIR}/windows/1_SETUP.bat"        "${DIST_DIR}/1_SETUP.bat"
cp "${DIST_DIR}/windows/2_START.bat"        "${DIST_DIR}/2_START.bat"
cp "${DIST_DIR}/windows/3_STOP.bat"         "${DIST_DIR}/3_STOP.bat"
cp "${DIST_DIR}/windows/SETUP_PYTHON.bat"   "${DIST_DIR}/SETUP_PYTHON.bat"
cp "${DIST_DIR}/windows/START_PYTHON.bat"   "${DIST_DIR}/START_PYTHON.bat"
cp "${DIST_DIR}/windows/README_WINDOWS.txt" "${DIST_DIR}/README_WINDOWS.txt"

# ── macOS: fix executable permissions on shell scripts ───────────────────────
echo ""
echo "  [4/5] Fixing macOS executable permissions..."
chmod +x "${DIST_DIR}/mac/1_SETUP.sh"
chmod +x "${DIST_DIR}/mac/2_START.sh"
chmod +x "${DIST_DIR}/mac/3_STOP.sh"
chmod +x "${DIST_DIR}/Launch TRUTHFORGE.command" 2>/dev/null || true
cp "${DIST_DIR}/mac/README_MAC.txt" "${DIST_DIR}/README_MAC.txt"

# ── Create a combined README at root ─────────────────────────────────────────
cat > "${DIST_DIR}/README_INSTALL.txt" << 'READMEOF'
============================================================
  TRUTHFORGE AI  v1.1  |  Installation Guide
============================================================

  macOS users  → Read README_MAC.txt
  Windows users → Read README_WINDOWS.txt

------------------------------------------------------------
  WHAT'S IN THIS ZIP
------------------------------------------------------------

  mac/              macOS setup & launch scripts
  windows/          Windows setup & launch scripts
  agents/           AI pipeline agents
  core/             Core modules (state, logger, memory, etc.)
  ui/               Streamlit web interface
  scripts/          Load test and utility scripts
  tests/            Automated test suite
  docs/             Architecture diagrams & security docs
  sample_transcripts/  Example transcripts to try

------------------------------------------------------------
  QUICK START
------------------------------------------------------------

  macOS:    bash mac/1_SETUP.sh   (then bash mac/2_START.sh)
  Windows:  Double-click 1_SETUP.bat  (then 2_START.bat)

  You need ONE API key from one of these providers:
    OpenAI:    https://platform.openai.com/api-keys
    Anthropic: https://console.anthropic.com/
    Google:    https://aistudio.google.com/

============================================================
READMEOF

# ── Build the ZIP ─────────────────────────────────────────────────────────────
echo ""
echo "  [5/5] Creating ZIP archive..."
cd /tmp
zip -r "${OUTPUT_ZIP}" "${DIST_NAME}" \
  -x "*.DS_Store" \
  -x "*/__pycache__/*" \
  -x "*/*.pyc"

# ── Final security verification ───────────────────────────────────────────────
echo ""
echo "  Verifying .env is NOT in the archive..."
if unzip -l "${OUTPUT_ZIP}" 2>/dev/null | grep -q '[^.example]\.env$'; then
  echo "  [!!!] WARNING: .env found in zip! Please check manually."
  exit 1
else
  echo "  [✓] Confirmed — no .env file in zip."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
ZIP_SIZE=$(du -sh "${OUTPUT_ZIP}" | cut -f1)
FILE_COUNT=$(unzip -l "${OUTPUT_ZIP}" 2>/dev/null | tail -1 | awk '{print $2}')
echo ""
echo "  ============================================================"
echo "   Done!"
echo "   Output: ${OUTPUT_ZIP}"
echo "   Size:   ${ZIP_SIZE}    Files: ${FILE_COUNT}"
echo ""
echo "   macOS  → README_MAC.txt     Windows → README_WINDOWS.txt"
echo ""
echo "   Share ${DIST_NAME}.zip with anyone on Mac or Windows."
echo "   They do NOT need your .env — they create their own API key."
echo "  ============================================================"
echo ""
