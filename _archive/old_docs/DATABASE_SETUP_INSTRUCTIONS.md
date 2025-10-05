# Database Setup Instructions for Helios V3.0

## Current Status

✅ **Tier 1 Complete** - Data ingestion and feature engineering are fully operational:
- WebSocket client receiving live VALR data
- Multi-timeframe candle aggregator (1m, 5m, 15m)
- 90-feature engineering system

❌ **Databases Not Running** - Need to start PostgreSQL, Redis, and InfluxDB

---

## Quick Start (Recommended)

### Step 1: Start Docker Desktop

1. Press **Windows key**
2. Type **"Docker Desktop"**
3. Click on **Docker Desktop** to launch it
4. Wait for Docker Desktop to fully start
   - Look for the whale icon in your system tray
   - It should say "Docker Desktop is running"
5. **IMPORTANT**: Docker must be fully started before proceeding

### Step 2: Start Databases

Double-click: **`START_DATABASES.bat`**

This will:
- Start PostgreSQL (port 5432)
- Start Redis (port 6379)
- Start InfluxDB (port 8086)
- Start pgAdmin web UI (port 5050)

### Step 3: Setup Database Schema

Open Command Prompt in the project directory and run:

```bash
python setup_database.py
```

This will:
- Test PostgreSQL connection
- Create `helios_v3` database if it doesn't exist
- Test Redis connection
- Create all database tables and schemas
- Verify the setup

### Step 4: Verify Everything Works

```bash
python test_database_connections.py
```

---

## What Each Database Does

### PostgreSQL (Port 5432)
**Purpose**: Main relational database

**Stores**:
- Trading orders and positions
- Portfolio holdings
- ML model predictions
- LLM strategic decisions
- Risk metrics and limits
- System configuration
- User accounts (future)

**Tables Created**: 21 tables including:
- `market_ohlc` - Candlestick data
- `ml_predictions` - Neural network outputs
- `positions` - Current trading positions
- `orders` - Order history
- `risk_metrics` - Real-time risk data
- `portfolio_snapshots` - Historical portfolio states

### Redis (Port 6379)
**Purpose**: High-speed cache and real-time data

**Stores**:
- Current market prices (updated every second)
- Order book snapshots
- Real-time risk metrics
- Session data
- Rate limiting counters
- WebSocket connection state
- Feature vector cache

**Key Patterns**:
- `market:BTCZAR:price` - Latest price
- `orderbook:BTCZAR:snapshot` - Current order book
- `features:BTCZAR:latest` - Latest feature vector
- `risk:portfolio:current` - Current risk metrics

### InfluxDB (Port 8086)
**Purpose**: Time-series database for high-frequency data

**Stores**:
- Every trade tick (timestamp, price, volume)
- 1-second OHLC candles
- Orderbook depth over time
- Latency metrics
- Performance monitoring data

**Buckets**:
- `market_data` - All market data
- `system_metrics` - Performance data

### pgAdmin (Port 5050)
**Purpose**: Web-based PostgreSQL management

**Access**:
- URL: http://localhost:5050
- Email: admin@helios.local
- Password: admin

**Use For**:
- Viewing tables and data
- Running SQL queries
- Database maintenance
- Performance analysis

---

## Manual Docker Commands (if needed)

### Start Databases
```bash
cd C:\Jupyter\New_Valr
docker-compose -f docker-compose.databases.yml up -d
```

### Check Status
```bash
docker ps
```

You should see:
- `helios_postgres` - Running
- `helios_redis` - Running
- `helios_influxdb` - Running
- `helios_pgadmin` - Running

### View Logs
```bash
# All databases
docker-compose -f docker-compose.databases.yml logs -f

# Specific database
docker logs helios_postgres
docker logs helios_redis
docker logs helios_influxdb
```

### Stop Databases
```bash
docker-compose -f docker-compose.databases.yml down
```

### Reset Everything (CAUTION: Deletes all data!)
```bash
docker-compose -f docker-compose.databases.yml down -v
```

---

## Connection Details

### From Python (Helios Application)

Connections are automatically configured via `.env` file:

```python
from config.settings import settings

# PostgreSQL
postgres_url = settings.database.postgres_url
# postgresql+asyncpg://helios:password@localhost:5432/helios_v3

# Redis
redis_url = settings.database.redis_url
# redis://localhost:6379/0
```

### From Command Line

**PostgreSQL (psql)**:
```bash
# Using Docker
docker exec -it helios_postgres psql -U helios -d helios_v3

# If PostgreSQL installed locally
psql -U helios -d helios_v3 -h localhost -p 5432
```

**Redis (redis-cli)**:
```bash
# Using Docker
docker exec -it helios_redis redis-cli

# If Redis installed locally
redis-cli -h localhost -p 6379
```

**InfluxDB (Web UI)**:
- Open browser: http://localhost:8086
- Username: helios
- Password: helios_dev_password

---

## Troubleshooting

### Error: "Docker Desktop is not running"

**Solution**: Start Docker Desktop and wait for it to fully start (whale icon in system tray should be stable).

### Error: "Port 5432 already in use"

**Cause**: Another PostgreSQL instance is running

**Solution**:
```bash
# Stop local PostgreSQL
net stop postgresql-x64-14

# Or change port in docker-compose.databases.yml
ports:
  - "5433:5432"  # Use port 5433 instead
```

### Error: "Connection refused" when running setup_database.py

**Causes**:
1. Docker containers not started
2. Containers still initializing

**Solution**:
```bash
# Check container health
docker ps

# Wait for containers to be healthy (may take 30 seconds)
docker-compose -f docker-compose.databases.yml ps

# Check logs for errors
docker-compose -f docker-compose.databases.yml logs
```

### Error: "Password authentication failed"

**Cause**: .env password doesn't match container password

**Solution**:
1. Check `.env` file: `POSTGRES_PASSWORD=helios_secure_password_123`
2. Recreate containers:
```bash
docker-compose -f docker-compose.databases.yml down -v
docker-compose -f docker-compose.databases.yml up -d
```

---

## Next Steps After Database Setup

Once databases are running and schema is created:

1. ✅ **Test Data Persistence**
   - Save candles to PostgreSQL
   - Cache features in Redis
   - Store ticks in InfluxDB

2. ✅ **Start Full Application**
   ```bash
   python main.py
   ```
   - FastAPI server on http://localhost:8000
   - Complete API with database backing
   - Real-time WebSocket data flowing to storage

3. ✅ **Build Tier 2** - Neural Network Model
   - 40M parameter model
   - Training pipeline
   - Inference service

4. ✅ **Complete Trading System**
   - Risk management (GARCH + Kelly)
   - LLM strategic layer
   - Portfolio optimization
   - Auto-trading orchestrator

---

## Current Environment

```
Project: Helios V3.0 Trading System
Location: C:\Jupyter\New_Valr
Platform: Windows 11

Infrastructure:
  ✅ Python 3.12.7
  ✅ Docker Desktop installed
  ⏸️ PostgreSQL (via Docker) - NEEDS TO START
  ⏸️ Redis (via Docker) - NEEDS TO START
  ⏸️ InfluxDB (via Docker) - NEEDS TO START

Tier 1 Status: ✅ COMPLETE
  ✅ VALR WebSocket client
  ✅ Multi-timeframe candle aggregator
  ✅ 90-feature engineering system

Database Status: ⏸️ READY TO START
  📝 Docker Compose file ready
  📝 Setup script ready
  📝 Schema file ready (21 tables)
  🚀 Just need to start Docker Desktop and run START_DATABASES.bat
```

---

**To proceed, please:**
1. Start Docker Desktop
2. Run `START_DATABASES.bat`
3. Run `python setup_database.py`
4. Verify with `docker ps`

Then we'll have full database support and can continue building the trading system!
