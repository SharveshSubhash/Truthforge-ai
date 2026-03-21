@echo off
title TRUTHFORGE AI

echo.
echo  ============================================================
echo    TRUTHFORGE AI  ^|  Starting (Native Python)
echo  ============================================================
echo.

cd /d "%~dp0.."

if not exist "venv\Scripts\activate.bat" (
    echo  [!] Virtual environment not found. Run SETUP_PYTHON.bat first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo  [!] .env file not found. Run SETUP_PYTHON.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo  Starting TRUTHFORGE AI...
echo  Opening browser at http://localhost:8501
echo  Press Ctrl+C in this window to stop.
echo.

start /b "" timeout /t 3 /nobreak >nul && start http://localhost:8501

streamlit run main.py --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
