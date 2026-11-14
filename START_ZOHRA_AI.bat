@echo off
setlocal
title ZOHRA AI - Quantitative Trading OS and JARVIS Voice Companion
color 0B

cd /d "%~dp0"
if not exist "zohra_talk.py" (
    cd /d "c:\Users\dell\Desktop\trading_bot"
)

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=c:\Users\dell\Desktop\trading_bot\.venv\Scripts\python.exe"
)
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

:MENU
cls
echo ===============================================================================
echo            ZOHRA AI - UNIFIED TRADING OS ^& JARVIS COMPANION
echo ===============================================================================
echo.
echo   [1] Start JARVIS Voice Companion  (Talk in Hindi / English / Hinglish)
echo   [2] Start Unified Trading Engine   (3 MT5 Accounts, 15 Strategies)
echo   [3] Start Full Suite               (Trading Engine + Voice Companion)
echo   [4] Start Mission Control Dashboard (FastAPI Web UI on port 8001)
echo   [5] Check Trading System Status
echo   [6] Exit
echo.
echo ===============================================================================
set "choice=1"
set /p choice="Select an option (1-6) [Default: 1]: "

if "%choice%"=="1" goto VOICE
if "%choice%"=="2" goto TRADING
if "%choice%"=="3" goto FULL_SUITE
if "%choice%"=="4" goto DASHBOARD
if "%choice%"=="5" goto STATUS
if "%choice%"=="6" goto EXIT

echo Invalid choice. Please enter 1, 2, 3, 4, 5, or 6.
ping 127.0.0.1 -n 2 >nul
goto MENU

:VOICE
cls
echo Starting Zohra JARVIS Voice Companion...
echo -------------------------------------------------------------------------------
"%PYTHON_EXE%" zohra_talk.py
pause
goto MENU

:TRADING
cls
echo Starting Zohra Unified Multi-Account Trading Engine...
echo -------------------------------------------------------------------------------
"%PYTHON_EXE%" zohra.py
pause
goto MENU

:FULL_SUITE
cls
echo Launching Complete Zohra System...
echo -------------------------------------------------------------------------------
echo [1/2] Starting Unified Trading Engine in background window...
start "Zohra Trading Engine" cmd /k ""%PYTHON_EXE%" zohra.py"
ping 127.0.0.1 -n 2 >nul
echo [2/2] Starting JARVIS Voice Companion in this window...
"%PYTHON_EXE%" zohra_talk.py
pause
goto MENU

:DASHBOARD
cls
echo Starting Zohra Mission Control Dashboard on http://localhost:8001 ...
echo -------------------------------------------------------------------------------
start http://localhost:8001
"%PYTHON_EXE%" -m uvicorn zohra.api.app:app --host 0.0.0.0 --port 8001 --reload
pause
goto MENU

:STATUS
cls
echo Querying Zohra Trading System Status...
echo -------------------------------------------------------------------------------
"%PYTHON_EXE%" run_zohra_unified.py --status
echo.
pause
goto MENU

:EXIT
echo Exiting Zohra AI. Have a great day!
ping 127.0.0.1 -n 2 >nul
exit /b 0
