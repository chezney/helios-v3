@echo off
REM Helios V3.0 - Simplified Setup (No Database Required for Testing)

echo ============================================================
echo   Helios V3.0 - Quick Setup
echo ============================================================
echo.

echo [1/3] Checking Python...
python --version
if %errorLevel% neq 0 (
    echo ERROR: Python not found
    pause
    exit /b 1
)
echo.

echo [2/3] Installing Python packages...
pip install --upgrade pip
pip install -q fastapi uvicorn pydantic pydantic-settings python-dotenv aiohttp websockets
echo Core packages installed
echo.

echo [3/3] Creating directories...
if not exist logs mkdir logs
if not exist models mkdir models
echo Directories created
echo.

echo ============================================================
echo   Quick Setup Complete!
echo ============================================================
echo.
echo You can now:
echo.
echo 1. Test modular architecture:
echo    python test_modularity.py
echo.
echo 2. Test VALR connection (next step):
echo    python test_valr_connection.py
echo.
pause
