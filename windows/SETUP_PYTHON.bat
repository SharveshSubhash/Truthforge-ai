@echo off
setlocal enabledelayedexpansion
title TRUTHFORGE AI - Python Setup (No Docker)

echo.
echo  ============================================================
echo    TRUTHFORGE AI  ^|  Native Python Setup
echo    (Use this only if you don't have Docker)
echo  ============================================================
echo.

cd /d "%~dp0.."

:: ── Check Python 3.11+ ───────────────────────────────────────────────────────
echo  [1/5] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Python is NOT installed.
    echo  Please install Python 3.11 from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python %PYVER% found.

:: Basic version check
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo  [!] Python 3.11+ required. Found %PYVER%
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 (
    if %PY_MINOR% LSS 11 (
        echo  [!] Python 3.11+ required. Found %PYVER%
        echo  Download: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)
echo.

:: ── Create virtual environment ───────────────────────────────────────────────
echo  [2/5] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo  Virtual environment created.
) else (
    echo  Virtual environment already exists.
)
echo.

:: ── Install dependencies ─────────────────────────────────────────────────────
echo  [3/5] Installing dependencies (this may take 5-10 minutes)...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo  [ERROR] Dependency installation failed.
    pause
    exit /b 1
)
echo  Dependencies installed.
echo.

:: ── Download spaCy model ─────────────────────────────────────────────────────
echo  [4/5] Downloading language model...
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo  [ERROR] spaCy model download failed. Check your internet connection.
    pause
    exit /b 1
)
echo  Language model downloaded.
echo.

:: ── Set up .env ──────────────────────────────────────────────────────────────
echo  [5/5] Setting up API keys...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo  Created .env from template.
    echo.
    echo  ============================================================
    echo   IMPORTANT: Edit the .env file and add your API key!
    echo  ============================================================
    echo.
    start notepad "%cd%\.env"
    echo  Press any key after saving your API key...
    pause >nul
) else (
    echo  .env file already exists. OK.
)
echo.

echo  ============================================================
echo   Setup complete! Run START_PYTHON.bat to launch the app.
echo  ============================================================
echo.
pause
