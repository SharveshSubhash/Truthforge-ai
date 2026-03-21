============================================================
  TRUTHFORGE AI  |  Windows Quick Start Guide  (v1.1)
============================================================

TRUTHFORGE AI detects inconsistencies in court transcripts
using a multi-agent AI pipeline (LangGraph + GPT-4o / Claude).

------------------------------------------------------------
  OPTION A: Docker (Recommended — easiest)
------------------------------------------------------------

STEP 1 — Install Docker Desktop
  Download from: https://www.docker.com/products/docker-desktop/
  * Check "Use WSL 2" during install (it will prompt you)
  * Restart your PC after install

STEP 2 — First-time setup
  Double-click:  1_SETUP.bat
  * This builds the app image (~5-10 min first time)
  * It will open .env in Notepad — add your API key there

STEP 3 — Add your API key in .env
  Open the .env file (in the main project folder) and set:
    OPENAI_API_KEY=sk-...your key here...
  Save and close.

STEP 4 — Start the app
  Double-click:  2_START.bat
  * Browser opens automatically at http://localhost:8501

STEP 5 — Stop the app when done
  Double-click:  3_STOP.bat

------------------------------------------------------------
  OPTION B: Native Python (No Docker needed)
------------------------------------------------------------

STEP 1 — Install Python 3.11
  Download from: https://www.python.org/downloads/
  IMPORTANT: Check "Add Python to PATH" during install!

STEP 2 — First-time setup
  Double-click:  SETUP_PYTHON.bat
  * Installs all dependencies (~5 min)
  * Opens .env in Notepad — add your API key

STEP 3 — Start the app
  Double-click:  START_PYTHON.bat
  * Browser opens at http://localhost:8501
  * Close the black window to stop

------------------------------------------------------------
  GETTING AN API KEY
------------------------------------------------------------

OpenAI (GPT-4o Mini — recommended, affordable):
  https://platform.openai.com/api-keys

Anthropic (Claude):
  https://console.anthropic.com/

Google (Gemini):
  https://aistudio.google.com/

You only need ONE key to use the app.

------------------------------------------------------------
  USING THE APP
------------------------------------------------------------

1. Open http://localhost:8501 in your browser
2. Pick your AI model in the left sidebar
3. Upload a transcript (.txt, .pdf, or .docx)
   OR paste text directly in the text box
4. Click "Analyse Transcript"
5. Review results across 9 tabs:
   Tab 1  — Inconsistencies     (HIGH / MEDIUM / LOW severity)
   Tab 2  — Timeline            (reconstructed event sequence)
   Tab 3  — Entities            (people, places, dates extracted)
   Tab 4  — Explanations        (plain-language reasoning)
   Tab 5  — Responsible AI      (bias / fairness checks)
   Tab 6  — Memory              (persistent fact store)
   Tab 7  — Audit Log           (every decision logged)
   Tab 8  — Full Report         (download as Markdown)
   Tab 9  — Security Analytics  (run metrics & event telemetry)
6. Download the full report from Tab 8

------------------------------------------------------------
  TROUBLESHOOTING
------------------------------------------------------------

"Docker not running" error
  → Open Docker Desktop from the Start Menu / taskbar

Browser shows "This site can't be reached"
  → Wait 30 seconds and refresh; the app is still starting

"No module named X" error (Python mode)
  → Re-run SETUP_PYTHON.bat

API key not working
  → Check your .env file has no extra spaces around the key
  → Make sure the key starts with "sk-" (OpenAI) or "sk-ant-" (Anthropic)

App is slow
  → Normal! LLM calls take 10-60s per transcript
  → Rule-based mode (select "Rule-based (No LLM)") is instant

============================================================
  Need help? Share the error message from the black window.
============================================================
