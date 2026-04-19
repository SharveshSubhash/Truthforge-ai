@echo off
title TRUTHFORGE AI - Stopping

echo.
echo  ============================================================
echo    TRUTHFORGE AI  ^|  Stopping Application
echo  ============================================================
echo.

cd /d "%~dp0.."

docker-compose down
if errorlevel 1 (
    echo  [!] Could not stop cleanly. Try Docker Desktop to stop manually.
) else (
    echo  TRUTHFORGE AI stopped successfully.
)
echo.
pause
