@echo off
REM Helios V3.0 - Start PostgreSQL Database with Docker
REM Following PRD Section 3: "PostgreSQL only (Redis for caching if needed)"

echo.
echo ================================================================================
echo   HELIOS V3.0 - DATABASE STARTUP
echo   PostgreSQL Only (as per PRD)
echo ================================================================================
echo.

REM Check if Docker Desktop is running
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running!
    echo.
    echo Please start Docker Desktop first:
    echo   1. Press Windows key
    echo   2. Type "Docker Desktop"
    echo   3. Click on Docker Desktop to start it
    echo   4. Wait for Docker Desktop to fully start (whale icon in system tray)
    echo   5. Run this script again
    echo.
    pause
    exit /b 1
)

echo [OK] Docker Desktop is running
echo.

REM Stop any existing containers
echo [INFO] Stopping any existing Helios database containers...
docker-compose -f docker-compose.databases.yml down 2>nul

echo.
echo [INFO] Starting PostgreSQL database container...
echo   - PostgreSQL (port 5432) - PRIMARY DATABASE
echo   - As per PRD: "PostgreSQL only (Redis for caching if needed)"
echo.

REM Start containers
docker-compose -f docker-compose.databases.yml up -d

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start container!
    pause
    exit /b 1
)

echo.
echo [INFO] Waiting for PostgreSQL to be ready...
timeout /t 10 /nobreak >nul

echo.
echo ================================================================================
echo   CHECKING DATABASE STATUS
echo ================================================================================
echo.

REM Check container status
docker-compose -f docker-compose.databases.yml ps

echo.
echo ================================================================================
echo   DATABASE CONNECTION
echo ================================================================================
echo.
echo   PostgreSQL:
echo     Host: localhost
echo     Port: 5432
echo     Database: helios_v3
echo     User: helios
echo     Password: (see .env file - POSTGRES_PASSWORD)
echo.
echo ================================================================================
echo   NEXT STEPS
echo ================================================================================
echo.
echo   1. Verify container is healthy: docker ps
echo   2. Run database setup: python setup_database.py
echo   3. Start Helios application: python main.py
echo.
echo ================================================================================
echo.

pause
