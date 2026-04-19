#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# TRUTHFORGE AI — Launch TRUTHFORGE.command
# Double-click this file in Finder to open the launcher GUI directly.
# No terminal window will appear after the GUI opens.
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")"

# Run the Python GUI launcher (suppress terminal by detaching)
python3 launcher.py &

# Close the Terminal window that opened (macOS only)
sleep 0.5
osascript -e 'tell application "Terminal"
    set windowList to every window
    repeat with w in windowList
        if (count of tabs of w) = 1 then
            close w
        end if
    end repeat
end tell' 2>/dev/null || true
