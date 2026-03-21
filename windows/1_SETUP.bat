@echo off
setlocal enabledelayedexpansion
title TRUTHFORGE AI - First-Time Setup

echo.
echo  ============================================================
echo    TRUTHFORGE AI  ^|  First-Time Setup
echo  ============================================================
echo.

:: ── Check for Docker ─────────────────────────────────────────────────────────
echo  [1/4] Checking for Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Docker is NOT installed.
    echo.
    echo  Please install Docker Desktop for Windows:
    echo  https://www.docker.com/products/docker-desktop/
    echo.
    echo  After installing, restart this setup.
    echo.
    pause
    start https://www.docker.com/products/docker-desktop/
    exit /b 1
)
docker --version
echo  Docker found. OK.
echo.

:: ── Check Docker daemon is running ───────────────────────────────────────────
echo  [2/4] Checking Docker is running...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Docker Desktop is installed but NOT running.
    echo      Please start Docker Desktop from the taskbar and try again.
    echo.
    pause
    exit /b 1
)
echo  Docker daemon is running. OK.
echo.

:: ── Set up .env file ─────────────────────────────────────────────────────────
echo  [3/4] Setting up API keys...
cd /d "%~dp0.."

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo  Created .env from template.
    ) else (
        echo  OPENAI_API_KEY=your_openai_api_key_here> .env
        echo  ANTHROPIC_API_KEY=your_anthropic_api_key_here>> .env
        echo  GOOGLE_API_KEY=your_google_api_key_here>> .env
        echo  Created blank .env file.
    )
    echo.
    echo  ============================================================
    echo   IMPORTANT: Edit the .env file and add your API key!
    echo   The file is located at:
    echo   %cd%\.env
    echo  ============================================================
    echo.
    echo  Opening .env in Notepad for you to edit...
    start notepad "%cd%\.env"
    echo.
    echo  After saving your API key, press any key to continue...
    pause >nul
) else (
    echo  .env file already exists. OK.
)
echo.

:: ── Build Docker image ───────────────────────────────────────────────────────
echo  [4/4] Building TRUTHFORGE Docker image...
echo  (This may take 5-10 minutes on first run - downloading dependencies)
echo.
docker-compose build --no-cache
if errorlevel 1 (
    echo.
    echo  [ERROR] Docker build failed. Check the error above.
    pause
    exit /b 1
)
echo.
echo  ============================================================
echo   Setup complete! Run 2_START.bat to launch TRUTHFORGE AI.
echo  ============================================================
echo.
pause
