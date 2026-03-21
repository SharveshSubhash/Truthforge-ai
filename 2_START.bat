@echo off
setlocal enabledelayedexpansion
title TRUTHFORGE AI - Starting...

echo.
echo  ============================================================
echo    TRUTHFORGE AI  ^|  Starting Application
echo  ============================================================
echo.

:: Change to project root (one folder up from windows/)
cd /d "%~dp0.."

:: Check .env exists
if not exist ".env" (
    echo  [!] No .env file found. Please run 1_SETUP.bat first.
    echo.
    pause
    exit /b 1
)

:: Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo  [!] Docker Desktop is not running.
    echo      Please start Docker Desktop from the system tray and try again.
    echo.
    pause
    exit /b 1
)

:: Check if image exists; build if not
docker image inspect truthforge:latest >nul 2>&1
if errorlevel 1 (
    echo  [!] Docker image not found. Building now...
    docker-compose build
    if errorlevel 1 (
        echo  [ERROR] Build failed. Please run 1_SETUP.bat first.
        pause
        exit /b 1
    )
)

echo  Starting TRUTHFORGE AI...
echo.
docker-compose up -d

if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to start. Check Docker Desktop for details.
    pause
    exit /b 1
)

echo.
echo  Waiting for app to be ready...
timeout /t 5 /nobreak >nul

:: Wait for health check (up to 60s)
set /a attempts=0
:wait_loop
    set /a attempts+=1
    curl -s -f http://localhost:8501/_stcore/health >nul 2>&1
    if not errorlevel 1 goto app_ready
    if %attempts% geq 12 goto timeout_warn
    echo  Still starting... (%attempts%/12)
    timeout /t 5 /nobreak >nul
    goto wait_loop

:timeout_warn
echo  App is taking longer than expected to start.
echo  Try opening http://localhost:8501 in your browser manually.
goto open_browser

:app_ready
echo  App is ready!

:open_browser
echo.
echo  ============================================================
echo   TRUTHFORGE AI is running!
echo   Opening browser: http://localhost:8501
echo  ============================================================
echo.
start http://localhost:8501

echo  To stop the app, run 3_STOP.bat
echo.
pause
