# HELIOS V3.0 - Setup Guide

Quick start guide for setting up and running the Helios Trading System V3.0 Phase 1.

---

## Prerequisites

- Python 3.12+
- PostgreSQL 14+
- VALR API account (for live trading later)

---

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=helios
POSTGRES_USER=helios_user
POSTGRES_PASSWORD=your_secure_password

# Trading Configuration
TRADING_PAIRS=BTCZAR,ETHZAR,SOLZAR
VALR_WEBSOCKET_URL=wss://api.valr.com/ws/trade
VALR_API_BASE_URL=https://api.valr.com

# API Keys (for Phase 6 - Live Trading)
# VALR_API_KEY=your_api_key
# VALR_API_SECRET=your_api_secret
```

### 3. Create Database

```sql
CREATE DATABASE helios;
CREATE USER helios_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE helios TO helios_user;
```

---

## Phase 1 Setup (Data Foundation)

### Step 1: Create Database Tables

```bash
python create_tier1_tables.py
```

**Output:**
```
[OK] market_ohlc created
[OK] engineered_features created
[OK] orderbook_snapshots created
[OK] market_trades created
[SUCCESS] TIER 1 TABLES CREATED SUCCESSFULLY
```

### Step 2: Start Server (🆕 AUTO-STARTS DATA COLLECTION) - UPDATED ARCHITECTURE

**NEW (October 2025):** Server now automatically starts real-time data collection with the **NEW HYBRID ARCHITECTURE**!

**ARCHITECTURE CHANGE (October 2025):**
- **PRIMARY:** VALRCandlePoller (REST API polling every 60s)
- **SUPPLEMENTARY:** VALRWebSocketClient (real-time prices ~1-5 per second)
- **DEPRECATED:** ~~LiveCandleGenerator~~ (removed - NEW_TRADE is account-only)

```bash
python main.py
```

**What Gets Auto-Started:**
- ✅ VALRCandlePoller polling `/v1/public/{pair}/buckets` API (official VALR candles)
- ✅ VALRWebSocketClient for MARKET_SUMMARY_UPDATE (real-time prices)
- ✅ AGGREGATED_ORDERBOOK_UPDATE for bid/ask spread features
- ✅ Live data flowing to database immediately (1m → 5m → 15m aggregation)
- ✅ All configured trading pairs subscribed

**Expected Server Output:**
```
[OK] Database connection verified
[OK] Tier 2 prediction service initialized
[OK] Tier 3 Aether Risk Engine initialized
[OK] Tier 5 Portfolio Manager initialized

[Tier 1] Starting data collection...
[Tier 1] VALRCandlePoller started (polling every 60s)
[Tier 1] VALRWebSocketClient started (real-time prices)
[Tier 1] Subscribed to BTCZAR (MARKET_SUMMARY_UPDATE + orderbook)
[Tier 1] Subscribed to ETHZAR (MARKET_SUMMARY_UPDATE + orderbook)
[Tier 1] Subscribed to SOLZAR (MARKET_SUMMARY_UPDATE + orderbook)
[OK] Tier 1 real-time data collection active for 3 pairs

Application startup complete. Ready to accept requests.
```

### Step 2b: Historical Backfill (Optional)

If you need historical data before the WebSocket started:

```bash
python scripts/smart_gap_backfill.py
```

**What it does:**
- Detects gaps in candle data
- Fetches ONLY missing trades from VALR API
- Aggregates into 1m, 5m, 15m candles
- Calculates 90 features per timeframe
- Fills gaps in database

**Expected Duration:** ~2 minutes for 3 pairs (depends on gap size)

### Step 3: Verify Data Quality

```bash
python verify_tier1_data.py
```

**Checks:**
- ✅ No NULL values
- ✅ Price consistency (high >= low)
- ✅ Non-negative volumes
- ✅ Feature vector sizes (90 features each)

---

## Verify Installation

### Check Database Connection

```python
import asyncio
import asyncpg
from config.settings import settings

async def test_connection():
    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        database=settings.database.postgres_db,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password
    )

    count = await conn.fetchval("SELECT COUNT(*) FROM market_ohlc")
    print(f"✅ Connected! Found {count} candles")

    await conn.close()

asyncio.run(test_connection())
```

### Check Data

```sql
-- OHLC candles
SELECT pair, timeframe, COUNT(*) as count
FROM market_ohlc
GROUP BY pair, timeframe
ORDER BY pair, timeframe;

-- Feature vectors
SELECT pair, COUNT(*) as count
FROM engineered_features
GROUP BY pair;
```

---

## Directory Structure

```
New_Valr/
├── config/
│   └── settings.py              # Configuration management
├── src/
│   ├── data/
│   │   ├── collectors/
│   │   │   ├── valr_websocket_client.py
│   │   │   └── historical_collector.py
│   │   ├── processors/
│   │   │   ├── candle_aggregator.py
│   │   │   └── feature_engineering.py
│   │   └── storage/
│   │       └── database_writer.py
│   └── utils/
│       └── logger.py
├── database/
│   └── schema.sql               # Complete database schema
├── create_tier1_tables.py       # Setup script
├── run_historical_backfill.py   # Backfill script
├── verify_tier1_data.py         # Verification script
├── PHASE_1_COMPLETE.md          # Phase 1 documentation
├── SETUP_GUIDE.md               # This file
└── .env                         # Environment variables (create this)
```

---

## Troubleshooting

### Database Connection Failed

```
[FAIL] Database connection failed: FATAL: password authentication failed
```

**Solution:** Check `.env` file credentials match your PostgreSQL setup.

### No Trades Fetched

```
WARNING: VALR API returned 0 trades
```

**Solution:** VALR API has rate limits. Wait 30 seconds and try again.

### Unicode Encoding Errors (Windows)

```
UnicodeEncodeError: 'charmap' codec can't encode character
```

**Solution:** This is cosmetic only. The script still works. Data is saved correctly.

---

## Next Steps

After Phase 1 setup is complete, proceed to Phase 2:

**Phase 2: Neural Network (Weeks 7-12)**
- Implement 40M parameter neural network
- Training pipeline
- Real-time inference engine

See `PHASE_1_COMPLETE.md` for detailed Phase 1 results.

---

## Support

For issues or questions:
1. Check `PHASE_1_COMPLETE.md` for detailed documentation
2. Review PRD: `docs/HELIOS_V3_COMPLETE_PRD.md`
3. Check logs in `logs/` directory

---

**Phase 1 Status:** ✅ COMPLETE
**Ready for:** Phase 2 - Neural Network Implementation
