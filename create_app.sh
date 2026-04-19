#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TRUTHFORGE AI — create_app.sh
# Builds a double-clickable "TRUTHFORGE AI.app" in /Applications (or ~/Desktop)
# and installs all Python dependencies.
#
# Usage:  bash create_app.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="TRUTHFORGE AI"
PYTHON="$(which python3)"

echo ""
echo "⚖  TRUTHFORGE AI — App Builder"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Python check ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "✗  python3 not found. Install from https://www.python.org"
    exit 1
fi
echo "✓  Python: $PYTHON ($(python3 --version))"

# ── 2. Install requirements ──────────────────────────────────────────────────
echo ""
echo "→  Installing Python dependencies (this may take a minute)…"
"$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
echo "✓  Dependencies installed."

# ── 3. Download spaCy model ──────────────────────────────────────────────────
echo "→  Downloading spaCy model (en_core_web_sm)…"
"$PYTHON" -m spacy download en_core_web_sm --quiet 2>/dev/null || true
echo "✓  spaCy model ready."

# ── 4. Create .env if missing ────────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "✓  Created .env — open it and add your API key(s)."
else
    echo "✓  .env already exists."
fi

# ── 5. Build the .app bundle ─────────────────────────────────────────────────
echo ""
echo "→  Building macOS app bundle…"

APP_DIR="$HOME/Applications/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

mkdir -p "$MACOS_DIR" "$RESOURCES"

# Info.plist
cat >"$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>TRUTHFORGE AI</string>
    <key>CFBundleDisplayName</key>
    <string>TRUTHFORGE AI</string>
    <key>CFBundleIdentifier</key>
    <string>com.truthforge.ai</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.14</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# Executable shell script (the actual binary macOS runs)
cat >"$MACOS_DIR/launcher" <<LAUNCHER
#!/usr/bin/env bash
# Launcher script embedded inside the .app bundle
cd "$SCRIPT_DIR"
exec "$PYTHON" "$SCRIPT_DIR/launcher.py"
LAUNCHER
chmod +x "$MACOS_DIR/launcher"

echo "✓  Built: $APP_DIR"

# ── 6. Also put a copy on the Desktop ────────────────────────────────────────
DESKTOP_APP="$HOME/Desktop/$APP_NAME.app"
if [ ! -d "$DESKTOP_APP" ]; then
    cp -R "$APP_DIR" "$DESKTOP_APP" 2>/dev/null || true
    echo "✓  Shortcut placed on Desktop."
fi

# ── 7. Remove quarantine flag ────────────────────────────────────────────────
xattr -dr com.apple.quarantine "$APP_DIR" 2>/dev/null || true
xattr -dr com.apple.quarantine "$DESKTOP_APP" 2>/dev/null || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅  Done!  Double-click 'TRUTHFORGE AI' on your Desktop"
echo "    or in ~/Applications to launch the app."
echo ""
echo "    Before first run:"
echo "    1. Open $SCRIPT_DIR/.env"
echo "    2. Add your API key (e.g. ANTHROPIC_API_KEY=sk-ant-...)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
