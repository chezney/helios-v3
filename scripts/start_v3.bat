@echo off
REM Helios Trading System V3.0 - Windows Startup Script

echo ==================================================
echo   Helios Trading System V3.0 - Starting Up
echo ==================================================
echo.

REM Check if .env file exists
if not exist .env (
    echo WARNING: .env file not found!
    echo Creating .env from .env.example...
    copy .env.example .env
    echo .env file created. Please edit it with your actual credentials.
    echo.
    echo Required variables to configure:
    echo   - POSTGRES_PASSWORD
    echo   - VALR_API_KEY
    echo   - VALR_API_SECRET
    echo   - ANTHROPIC_API_KEY (for LLM)
    echo   - OPENAI_API_KEY (for LLM backup)
    echo.
    pause
)

REM Check Python version
echo Checking Python version...
python --version
echo.

REM Create virtual environment if needed
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    echo Virtual environment created
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing/updating dependencies...
pip install -q -r requirements.txt
echo Dependencies installed
echo.

REM Create necessary directories
echo Creating directories...
if not exist logs mkdir logs
if not exist models mkdir models
if not exist database\migrations mkdir database\migrations
if not exist tests mkdir tests
echo Directories created
echo.

echo ==================================================
echo   Starting Helios Trading System V3.0
echo ==================================================
echo.

REM Start the application
python main_v3.py

pause
