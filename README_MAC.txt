============================================================
  TRUTHFORGE AI  |  macOS Quick Start Guide  (v1.1)
============================================================

TRUTHFORGE AI detects inconsistencies in court transcripts
using a multi-agent AI pipeline (LangGraph + GPT-4o / Claude).

------------------------------------------------------------
  OPTION A: Docker (Recommended — easiest)
------------------------------------------------------------

STEP 1 — Install Docker Desktop
  Download from: https://www.docker.com/products/docker-desktop/
  * Open Docker Desktop after install; wait for the whale
    icon to appear in the menu bar before continuing.

STEP 2 — First-time setup
  Open Terminal, then run:
    bash mac/1_SETUP.sh
  * Choose option 1 (Docker)
  * The script opens .env in TextEdit — add your API key there
  * First build takes 5-10 minutes

STEP 3 — Start the app
    bash mac/2_START.sh
  * Browser opens automatically at http://localhost:8501

STEP 4 — Stop the app when done
    bash mac/3_STOP.sh

------------------------------------------------------------
  OPTION B: Native Python (No Docker needed)
------------------------------------------------------------

STEP 1 — Install Python 3.11+
  Download from: https://www.python.org/downloads/
  (Python 3.13 also works)

STEP 2 — First-time setup
  Open Terminal in the project folder, then run:
    bash mac/1_SETUP.sh
  * Choose option 2 (Python)
  * Installs all dependencies (~5-10 min)
  * Opens .env in TextEdit — add your API key

STEP 3 — Start the app
    bash mac/2_START.sh
  * Browser opens at http://localhost:8501
  * Press Ctrl+C in Terminal to stop

------------------------------------------------------------
  QUICK LAUNCH (after setup is done)
------------------------------------------------------------

  Double-click "Launch TRUTHFORGE.command" in Finder
  to start the app without opening a Terminal window.

  Right-click → Open the first time macOS asks for permission.

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
  USING THE APP  (v1.1 features)
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
  → Open Docker Desktop from Applications and wait for
    the whale icon before re-running the script.

"Permission denied" running .sh files
  → Run:  chmod +x mac/*.sh  then try again.

macOS blocks "Launch TRUTHFORGE.command"
  → Right-click the file → Open → Open anyway.

"No module named X" error (Python mode)
  → Re-run mac/1_SETUP.sh (choose option 2).

API key not working
  → Check .env has no extra spaces around the key.
  → OpenAI keys start with "sk-", Anthropic with "sk-ant-".

App is slow
  → Normal — LLM calls take 10-60s per transcript.
  → Select "Rule-based (No LLM)" in the sidebar for instant
    results (no API key needed).

============================================================
  Need help? Share the error from your Terminal window.
============================================================
