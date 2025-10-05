# Tier 1 Tests - Data Foundation

**Status:** All tests passing ✅

---

## Test Files

### `test_tier1_with_database.py` ⭐ PRIMARY TEST

**Purpose:** Complete end-to-end Tier 1 pipeline test with database integration

**What it tests:**
- ✅ WebSocket connection to VALR exchange
- ✅ Real-time trade processing
- ✅ Multi-timeframe candle aggregation (1m, 5m, 15m)
- ✅ PostgreSQL database persistence
- ✅ Database verification

**How to run:**
```bash
cd tests/tier1
python test_tier1_with_database.py
```

**Duration:** 2 minutes (live data collection)

**Expected output:**
```
================================================================================
  TIER 1 COMPLETE PIPELINE TEST - WITH DATABASE
================================================================================

[INIT] DatabaseWriter ready
[INIT] Aggregator ready with database integration
[INIT] WebSocket client ready

[PROGRESS] Trades: 1,142, Candles: 6

[OK] TIER 1 COMPLETE - ALL TESTS PASSED
[OK] WebSocket -> Candles -> Database pipeline operational
```

---

### `test_valr_connection.py`

**Purpose:** Test VALR API authentication and account access

**What it tests:**
- ✅ API key authentication
- ✅ Account balance retrieval
- ✅ Trading pair verification

**How to run:**
```bash
python test_valr_connection.py
```

**Duration:** < 5 seconds

---

### `test_features_simple.py`

**Purpose:** Test feature engineering with mock data

**What it tests:**
- ✅ 90 feature calculation (30 per timeframe)
- ✅ No NaN values
- ✅ No Inf values
- ✅ Correct feature dimensions

**How to run:**
```bash
python test_features_simple.py
```

**Duration:** < 5 seconds

---

### `test_candle_aggregator.py`

**Purpose:** Test multi-timeframe candle aggregation

**What it tests:**
- ✅ 1m, 5m, 15m candle creation
- ✅ Proper OHLC calculation
- ✅ Trade count aggregation
- ✅ Volume tracking

**How to run:**
```bash
python test_candle_aggregator.py
```

**Duration:** < 5 seconds

---

### `setup_database.py`

**Purpose:** Initialize PostgreSQL database schema

**What it does:**
- Creates 21 tables for all 5 tiers
- Creates indexes for query optimization
- Verifies table creation

**How to run:**
```bash
python setup_database.py
```

**Duration:** < 10 seconds

---

## Test Results Summary

### Last Test Run: October 1, 2025

| Test | Status | Trades | Candles | DB Writes | Duration |
|------|--------|--------|---------|-----------|----------|
| **Full Pipeline** | ✅ PASS | 1,142 | 6 | 5/5 (100%) | 2 min |
| **VALR Connection** | ✅ PASS | - | - | - | < 5s |
| **Feature Engineering** | ✅ PASS | - | - | - | < 5s |
| **Candle Aggregator** | ✅ PASS | - | - | - | < 5s |
| **Database Setup** | ✅ PASS | - | - | 21 tables | < 10s |

---

## Running All Tests

```bash
# Run full test suite
cd tests/tier1

# 1. Setup database (first time only)
python setup_database.py

# 2. Test VALR connection
python test_valr_connection.py

# 3. Test feature engineering
python test_features_simple.py

# 4. Test candle aggregator
python test_candle_aggregator.py

# 5. Test complete pipeline (2-minute live test)
python test_tier1_with_database.py
```

**Total time:** ~3 minutes

---

## Troubleshooting

### Database Connection Error

**Error:** `password authentication failed for user "helios"`

**Solution:**
1. Check `.env` file has correct `POSTGRES_PASSWORD`
2. Restart PostgreSQL container: `docker-compose restart`
3. Verify container is running: `docker ps`

### WebSocket Connection Error

**Error:** `Failed to connect to wss://api.valr.com/ws/trade`

**Solution:**
1. Check internet connection
2. Verify VALR API is operational: https://www.valr.com/status
3. Check firewall settings

### No Candles Created

**Error:** `Candles Created: 0`

**Solution:**
1. Wait longer (need at least 1 minute for 1m candles)
2. Check if BTCZAR is trading (low volume = no trades)
3. Verify WebSocket is receiving trades: check `Messages Received` count

---

## Test Data Verification

### Check Database Contents

```bash
# View recent candles
docker exec helios_postgres psql -U helios -d helios_v3 -c "
SELECT pair, timeframe, open_time, close_price, num_trades
FROM market_ohlc
ORDER BY open_time DESC
LIMIT 10;
"

# Count candles by timeframe
docker exec helios_postgres psql -U helios -d helios_v3 -c "
SELECT timeframe, COUNT(*) as total
FROM market_ohlc
GROUP BY timeframe
ORDER BY timeframe;
"

# Database statistics
docker exec helios_postgres psql -U helios -d helios_v3 -c "
SELECT
    'market_ohlc' as table_name, COUNT(*) as row_count
FROM market_ohlc
UNION ALL
SELECT 'market_trades', COUNT(*) FROM market_trades
UNION ALL
SELECT 'orderbook_snapshots', COUNT(*) FROM orderbook_snapshots
UNION ALL
SELECT 'engineered_features', COUNT(*) FROM engineered_features;
"
```

---

## Next Tests (Tier 2)

- [ ] Neural network forward pass test
- [ ] Training pipeline test
- [ ] Inference service test
- [ ] End-to-end prediction test

---

**Last Updated:** October 1, 2025
