# Database Setup Guide for Helios V3.0

This guide will help you install and configure PostgreSQL and Redis on Windows 11.

## Prerequisites
- Windows 11
- Administrator access
- PowerShell or Command Prompt

---

## Option 1: Using Chocolatey (Recommended - Fastest)

### Step 1: Install Chocolatey (if not already installed)

Open PowerShell as Administrator and run:
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

### Step 2: Install PostgreSQL

```powershell
choco install postgresql14 -y
```

**Default Installation:**
- Location: `C:\Program Files\PostgreSQL\14\`
- Default User: `postgres`
- Default Port: `5432`

**Set Password for postgres user:**
```powershell
# After installation, open psql and set password
psql -U postgres
# In psql:
ALTER USER postgres PASSWORD 'your_secure_password';
\q
```

### Step 3: Install Redis

```powershell
choco install redis-64 -y
```

**Default Installation:**
- Location: `C:\Program Files\Redis\`
- Default Port: `6379`

**Start Redis as Windows Service:**
```powershell
redis-server --service-install
redis-server --service-start
```

---

## Option 2: Manual Installation

### PostgreSQL Manual Installation

1. **Download PostgreSQL 14:**
   - Visit: https://www.postgresql.org/download/windows/
   - Download the Windows installer (postgresql-14.x-x-windows-x64.exe)

2. **Run Installer:**
   - Double-click the downloaded file
   - Follow the installation wizard
   - Choose components: PostgreSQL Server, pgAdmin 4, Command Line Tools
   - Set password for postgres user (REMEMBER THIS!)
   - Default port: 5432
   - Default locale: Default

3. **Verify Installation:**
   ```cmd
   psql --version
   ```

### Redis Manual Installation

1. **Download Redis for Windows:**
   - Visit: https://github.com/tporadowski/redis/releases
   - Download the latest `Redis-x64-x.x.x.msi`

2. **Run Installer:**
   - Double-click the MSI file
   - Follow the installation wizard
   - Check "Add Redis to PATH"
   - Install as Windows Service

3. **Verify Installation:**
   ```cmd
   redis-cli --version
   ```

---

## Option 3: Using Docker (Recommended for Development)

### Step 1: Install Docker Desktop

1. Download Docker Desktop from: https://www.docker.com/products/docker-desktop
2. Install and restart your computer
3. Enable WSL2 backend in Docker Desktop settings

### Step 2: Create Docker Compose File

We already have `docker-compose.yml` in the project root. To start databases only:

```yaml
# docker-compose.databases.yml
version: '3.8'

services:
  postgres:
    image: postgres:14-alpine
    container_name: helios_postgres
    environment:
      POSTGRES_USER: helios
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: helios_v3
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: helios_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    command: redis-server --appendonly yes

volumes:
  postgres_data:
  redis_data:
```

### Step 3: Start Databases with Docker

```bash
cd C:\Jupyter\New_Valr
docker-compose -f docker-compose.databases.yml up -d
```

**Check if running:**
```bash
docker ps
```

**Access PostgreSQL:**
```bash
docker exec -it helios_postgres psql -U helios -d helios_v3
```

**Access Redis:**
```bash
docker exec -it helios_redis redis-cli
```

---

## After Installation: Configure Helios

### Step 1: Update .env File

Edit `C:\Jupyter\New_Valr\.env` and add:

```bash
# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=helios_v3
POSTGRES_USER=postgres      # or 'helios' if using Docker
POSTGRES_PASSWORD=your_secure_password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# InfluxDB (Optional - for time-series data)
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=
INFLUX_ORG=helios
INFLUX_BUCKET=market_data
```

### Step 2: Create Database and Schema

**Using PostgreSQL command line:**
```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE helios_v3;

# Connect to database
\c helios_v3

# Run schema file
\i C:/Jupyter/New_Valr/database/schema.sql

# Verify tables
\dt

# Exit
\q
```

**Using Python script (we'll create this):**
```bash
cd C:\Jupyter\New_Valr
python setup_database.py
```

### Step 3: Test Database Connections

Run the test script (we'll create this):
```bash
python test_database_connections.py
```

---

## Recommended Approach for You

Given that you're on Windows 11 and already using Docker for development:

**I recommend Option 3 (Docker)** because:
1. ✅ Easiest to set up and tear down
2. ✅ Isolated from your system
3. ✅ Consistent with the existing Docker setup
4. ✅ Easy to reset if something goes wrong
5. ✅ Matches production deployment approach

---

## Next Steps After Database Setup

1. ✅ Install PostgreSQL and Redis
2. Create database schema (run `database/schema.sql`)
3. Test database connections
4. Create data persistence layer (save candles and features to DB)
5. Start the main FastAPI application with full database support

---

## Troubleshooting

### PostgreSQL Not Starting
```bash
# Check if service is running
sc query postgresql-x64-14

# Start service
net start postgresql-x64-14
```

### Redis Not Starting
```bash
# Check if service is running
sc query Redis

# Start service
net start Redis
```

### Connection Refused Errors
- Check firewall settings (allow ports 5432 and 6379)
- Verify services are running
- Check `pg_hba.conf` for PostgreSQL authentication settings

---

Would you like me to proceed with Option 3 (Docker) setup?
