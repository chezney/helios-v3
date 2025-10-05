# Database Setup - PostgreSQL Only

**As per PRD Section 3: "PostgreSQL only (Redis for caching if needed)"**

## Quick Setup

### 1. Start Docker Desktop
- Press Windows key, type "Docker Desktop"
- Wait for it to fully start (whale icon in system tray)

### 2. Start PostgreSQL
```bash
START_DATABASES.bat
```

This starts PostgreSQL in a Docker container.

### 3. Setup Database Schema
```bash
python setup_database.py
```

This creates the `helios_v3` database and all 21 tables from the PRD schema.

### 4. Verify
```bash
docker ps
```

You should see `helios_postgres` running.

## Database Details

**PostgreSQL Container:**
- Host: `localhost`
- Port: `5432`
- Database: `helios_v3`
- User: `helios`
- Password: See `.env` file (`POSTGRES_PASSWORD`)

**Connect via psql:**
```bash
docker exec -it helios_postgres psql -U helios -d helios_v3
```

**Stop Database:**
```bash
docker-compose -f docker-compose.databases.yml down
```

**Reset All Data (CAUTION!):**
```bash
docker-compose -f docker-compose.databases.yml down -v
```

## What's Stored in PostgreSQL

As per PRD Section 32 (Complete Database Schema):

**Tier 1 - Data Foundation:**
- `market_ohlc` - OHLC candles (1m, 5m, 15m)
- `orderbook_snapshots` - Order book data
- `engineered_features` - 90 engineered features (JSONB format)
- `market_trades` - Individual trade records

**Tier 2 - Neural Network:**
- `ml_predictions` - Model predictions
- `ml_models` - Model versions

**Tier 3 - Risk Management:**
- `volatility_forecasts` - GARCH predictions
- `risk_metrics` - Current risk data

**Tier 4 - LLM:**
- `llm_decisions` - Strategic decisions
- `llm_contexts` - Market context

**Tier 5 - Portfolio:**
- `positions` - Current positions
- `orders` - Order history
- `portfolio_snapshots` - Historical states

**Total: 21 tables** covering all 5 tiers.

## Next Steps

After database is running:
1. Continue with Tier 2 - Neural Network implementation
2. All data will be persisted to PostgreSQL
3. No Redis, no InfluxDB (as per PRD simplification from V2.0)
