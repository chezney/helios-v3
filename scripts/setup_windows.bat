@echo off
REM Helios Trading System V3.0 - Windows Setup Script
REM This script installs and configures all required software

echo ============================================================
echo   Helios Trading System V3.0 - Windows Setup
echo ============================================================
echo.

REM Check if running as Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo [1/6] Checking Python installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)
python --version
echo.

echo [2/6] Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo Python dependencies installed
echo.

echo [3/6] Checking PostgreSQL...
where psql >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo PostgreSQL is NOT installed.
    echo.
    echo Please download and install PostgreSQL 14+ from:
    echo https://www.postgresql.org/download/windows/
    echo.
    echo After installation:
    echo 1. Note down the password you set for 'postgres' user
    echo 2. Run this script again
    echo.
    pause
    exit /b 1
) else (
    psql --version
    echo PostgreSQL is installed
)
echo.

echo [4/6] Checking Redis...
where redis-cli >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo Redis is NOT installed.
    echo.
    echo For Windows, Redis requires WSL2 or you can use Memurai (Redis alternative)
    echo.
    echo Option 1 - WSL2 + Redis (Recommended):
    echo   wsl --install
    echo   wsl
    echo   sudo apt update
    echo   sudo apt install redis-server
    echo   sudo service redis-server start
    echo.
    echo Option 2 - Memurai (Windows native):
    echo   Download from: https://www.memurai.com/get-memurai
    echo.
    echo Option 3 - Continue without Redis (Limited functionality):
    echo   The system will work but caching will be disabled
    echo.
    set /p SKIP_REDIS="Continue without Redis? (y/n): "
    if /i "%SKIP_REDIS%"=="n" (
        pause
        exit /b 1
    )
) else (
    redis-cli --version
    echo Redis is installed
)
echo.

echo [5/6] Creating directories...
if not exist logs mkdir logs
if not exist models mkdir models
if not exist database\migrations mkdir database\migrations
if not exist tests mkdir tests
echo Directories created
echo.

echo [6/6] Setup summary:
echo.
python --version
echo.

where psql >nul 2>&1
if %errorLevel% equ 0 (
    psql --version
) else (
    echo PostgreSQL: NOT INSTALLED (Required)
)
echo.

where redis-cli >nul 2>&1
if %errorLevel% equ 0 (
    redis-cli --version
) else (
    echo Redis: NOT INSTALLED (Optional)
)
echo.

echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo Next steps:
echo.
echo 1. Setup PostgreSQL database:
echo    setup_database.bat
echo.
echo 2. Test the installation:
echo    python test_modularity.py
echo.
echo 3. Start the application:
echo    python main_v3.py
echo.
pause
