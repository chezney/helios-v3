# 📊 Tier 1 - Visual Data Flow

**Real-time visualization of what happens in 2 minutes**

---

## 🌊 The Complete Data Stream (UPDATED ARCHITECTURE - October 2025)

**CRITICAL CHANGE:** VALR NEW_TRADE events are **account-only** (your executed orders), NOT public market data.
**NEW ARCHITECTURE:** Hybrid REST API (candles) + WebSocket (prices) approach.

```
                         VALR EXCHANGE (Bitcoin Trading)
                                    |
                    ┌───────────────┴───────────────┐
                    │                               │
         REST API /buckets              WebSocket MARKET_SUMMARY_UPDATE
         (Every 60 seconds)              (~1-5 updates/second)
                    │                               │
                    ▼                               ▼
        ┌─────────────────────┐       ┌─────────────────────────┐
        │ VALRCandlePoller    │       │ VALRWebSocketClient     │
        │ Official 1m candles │       │ Real-time prices        │
        │ (PRIMARY)           │       │ (SUPPLEMENTARY)         │
        └──────────┬──────────┘       └──────────┬──────────────┘
                   │                              │
                   │                              │ PRICE_UPDATE event
                   │                              │ (for position monitoring)
                   │                              │
                   ▼                              ▼
         [1-MIN CANDLE]                  [Real-time Price Cache]
         From VALR API                   <5 seconds fresh
         (Pre-aggregated)                (Sub-second SL/TP)
                   |
                   ▼
    ┌──────────────────────────────┐
    │   CANDLE AGGREGATOR          │
    │   - Aggregates 1m → 5m, 15m  │
    │   - Database-driven           │
    └──────────────┬───────────────┘
                   |
              ┌────┼─────┐
              |    |     |
         [1m] [5m] [15m]
         Every 1m  Every 5m  Every 15m
              |                     |                     |
              ▼                     ▼                     ▼
         ┌─────────┐           ┌─────────┐           ┌─────────┐
         │ OHLC    │           │ OHLC    │           │ OHLC    │
         │ O: 2019 │           │ O: 2019 │           │ O: 2019 │
         │ H: 2020 │           │ H: 2021 │           │ H: 2022 │
         │ L: 2018 │           │ L: 2017 │           │ L: 2016 │
         │ C: 2019 │           │ C: 2018 │           │ C: 2019 │
         └────┬────┘           └────┬────┘           └────┬────┘
              |                     |                     |
              └─────────────────────┴─────────────────────┘
                                    |
                                    ▼
                    ┌───────────────────────────────┐
                    │      FEATURE ENGINEER         │
                    │   - 30 features per timeframe │
                    │   - 90 features total         │
                    │   - MA, RSI, MACD, ATR, etc. │
                    └───────────────┬───────────────┘
                                    |
                    ┌───────────────┴───────────────┐
                    |                               |
                    ▼                               ▼
         ┌─────────────────────┐        ┌──────────────────────┐
         │  DATABASE WRITER    │        │  FEATURE VECTOR      │
         │  - Save candles     │        │  [90 numbers]        │
         │  - Save features    │        │  → ML Model (Tier 2) │
         └──────────┬──────────┘        └──────────────────────┘
                    |
                    ▼
         ┌──────────────────────────┐
         │   POSTGRESQL             │
         │   - market_ohlc          │
         │   - engineered_features  │
         │   - market_trades        │
         │   - orderbook_snapshots  │
         └──────────────────────────┘
```

---

## ⏱️ Timeline: First 5 Minutes

```
TIME      EVENT                                        DATABASE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

00:00     🟢 System starts
          ├─ PostgreSQL: Connected ✓
          ├─ VALRCandlePoller: Started (REST API polling) ✓
          ├─ WebSocket: Connected (MARKET_SUMMARY_UPDATE) ✓
          └─ Subscribed to BTCZAR ✓                   [Empty]

00:01-00:59 📊 Waiting for first 60-second poll...
          ├─ WebSocket receiving price updates (1-5/sec)
          ├─ Price cache updating in real-time
          └─ No candles yet (waiting for first API poll)

01:00     🎉 FIRST 1-MINUTE CANDLE!
          ├─ VALRCandlePoller fetches from /buckets API
          ├─ Official VALR 1m candle received
          ├─ 90 features calculated
          └─ Written to database ✓                    [1 candle]
                                                        ↓
                                                    market_ohlc:
                                                    ┌─────────────────┐
                                                    │ 1m @ 13:18:00  │
                                                    │ BTCZAR         │
                                                    │ 83 trades      │
                                                    └─────────────────┘

01:01-01:59 📊 Waiting for next 60-second poll...
          └─ WebSocket prices continue (~1-5/sec)     [1 candle]

02:00     🎉 SECOND 1-MINUTE CANDLE!
          ├─ VALRCandlePoller fetches next candle
          └─ Written to database ✓                    [2 candles]
                                                        ↓
                                                    market_ohlc:
                                                    ┌─────────────────┐
                                                    │ 1m @ 13:18:00  │
                                                    │ 1m @ 13:19:00  │
                                                    └─────────────────┘

03:00     🎉 THIRD 1-MINUTE CANDLE!
          └─ Written to database ✓                    [3 candles]

04:00     🎉 FOURTH 1-MINUTE CANDLE!
          └─ Written to database ✓                    [4 candles]

05:00     🎉🎉 FIRST 5-MINUTE CANDLE!!
          ├─ Combined 5× 1m candles
          ├─ OHLC calculated from all 5
          ├─ 90 features (for 5m timeframe)
          └─ Written to database ✓                    [5 candles]
                                                        ↓
                                                    market_ohlc:
                                                    ┌─────────────────┐
                                                    │ 1m @ 13:18:00  │
                                                    │ 1m @ 13:19:00  │
                                                    │ 1m @ 13:20:00  │
                                                    │ 1m @ 13:21:00  │
                                                    │ 5m @ 13:15:00  │ ← NEW!
                                                    └─────────────────┘

05:01     🎉 FIFTH 1-MINUTE CANDLE!
          └─ Written to database ✓                    [6 candles]

...       (continues...)
```

---

## 🔢 REST API Candle Fetching (NEW ARCHITECTURE)

### Example: Fetching Official VALR Candles

**OLD ARCHITECTURE (DEPRECATED):**
- WebSocket receives individual trades
- LiveCandleGenerator aggregates trades into candles
- Problem: NEW_TRADE events are account-only, not public data

**NEW ARCHITECTURE (CURRENT):**
```
VALRCandlePoller polls /v1/public/BTCZAR/buckets every 60s
                    ↓
        Fetches pre-aggregated 1m candles from VALR
                    ↓
               Duplicate detection
                    ↓
         Store candle in market_ohlc table
                    ↓
           Emit NEW_CANDLE event
```

### Example: 13:18:00 - 13:19:00 (1 minute)

```
REST API RESPONSE (Official VALR Candle)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trade #1  @ 13:18:00.123  →  R2,019,153  BUY  0.001  ┐
Trade #2  @ 13:18:02.456  →  R2,019,154  SELL 0.002  │
Trade #3  @ 13:18:05.789  →  R2,019,180  BUY  0.001  │
Trade #4  @ 13:18:08.012  →  R2,019,200  BUY  0.005  │ ← HIGHEST
Trade #5  @ 13:18:12.345  →  R2,019,190  SELL 0.003  │
...                                                    │
Trade #40 @ 13:18:35.678  →  R2,019,100  SELL 0.002  │ ← LOWEST
...                                                    │
Trade #83 @ 13:18:59.999  →  R2,019,153  BUY  0.001  ┘


CANDLE CREATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: Identify time window
        13:18:00 - 13:19:00 (floor to minute boundary)

Step 2: Extract OHLC
        OPEN  = First trade price   = R2,019,153 (Trade #1)
        HIGH  = Highest trade price = R2,019,200 (Trade #4)
        LOW   = Lowest trade price  = R2,019,100 (Trade #40)
        CLOSE = Last trade price    = R2,019,153 (Trade #83)

Step 3: Aggregate volume
        VOLUME = Sum all quantities = 0.001 + 0.002 + ... = 1.025 BTC

Step 4: Count trades
        TRADES = Total count = 83

Step 5: Create candle object
        ┌────────────────────────────────┐
        │ BTCZAR 1m @ 13:18:00          │
        │ ────────────────────────────  │
        │ Open:   R2,019,153            │
        │ High:   R2,019,200 (+R47)     │
        │ Low:    R2,019,100 (-R53)     │
        │ Close:  R2,019,153 (same)     │
        │ Volume: 1.025 BTC             │
        │ Trades: 83                    │
        └────────────────────────────────┘

Step 6: Write to database ✓
        INSERT INTO market_ohlc VALUES (...)

Step 7: Calculate features
        ┌────────────────────────────────┐
        │ FEATURE VECTOR (90 numbers)   │
        │ ────────────────────────────  │
        │ [1] return:        0.0000758  │
        │ [2] log_return:    0.00012    │
        │ [3] norm_price:    0.45       │
        │ [4] SMA_5:         2018930.60 │
        │ [5] SMA_10:        2018850.25 │
        │ ...                           │
        │ [90] kurtosis:     2.34       │
        └────────────────────────────────┘

Step 8: Store features ✓
        INSERT INTO engineered_features VALUES (...)
```

---

## 📊 Candle Visualization

### 1-Minute Candle (Candlestick Chart)

```
Price
  │
  │     HIGH: R2,019,200
  │        ╷
  │        │
  │     ┌──┴──┐  ← Close: R2,019,153
  │     │     │
  │     │     │
  │     │     │
  │     └──┬──┘  ← Open: R2,019,153
  │        │
  │        │
  │        ╵
  │     LOW: R2,019,100
  │
  └─────────────────────────── Time
      13:18:00 - 13:19:00


Interpretation:
- Body (rectangle): Open to Close
- Wicks (lines): High and Low extremes
- Color: Green if Close > Open (price up)
         Red if Close < Open (price down)
         White if Close = Open (same)
```

### 5-Minute Candle (Combining 5× 1m candles)

```
TIME:      13:15    13:16    13:17    13:18    13:19    13:20
           ├───────┼───────┼───────┼───────┼───────┤
           │       │       │       │       │       │
Prices:    2019.0  2018.5  2019.2  2019.1  2018.9  2019.0
           │       │       │       │       │       │
           └───────┴───────┴───────┴───────┴───────┘
                         │
                         ▼
              ONE 5-MINUTE CANDLE
              ┌────────────────────┐
              │ Open:  R2,019,000 │ ← From 13:15 candle
              │ High:  R2,019,200 │ ← Max of all 5
              │ Low:   R2,018,500 │ ← Min of all 5
              │ Close: R2,019,000 │ ← From 13:20 candle
              │ Volume: 5.125 BTC │ ← Sum of all 5
              │ Trades: 2,850     │ ← Sum of all 5
              └────────────────────┘
```

---

## 🎨 Feature Engineering Visualization

### How 90 Features Are Organized

```
CANDLE INPUT                    FEATURE CATEGORIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OHLC Data:                      [PRICE-BASED - 3 features]
  Open:  2019153                ├─ return
  High:  2019200                ├─ log_return
  Low:   2019100                └─ normalized_price
  Close: 2019153
                                [MOVING AVERAGES - 8 features]
Historical Data:                ├─ SMA_5, SMA_10, SMA_20, SMA_50
  Last 50 candles               └─ EMA_5, EMA_10, EMA_20, EMA_50

Price Movement:                 [MOMENTUM - 7 features]
  Up/down trends                ├─ RSI (Relative Strength)
                                ├─ MACD (Trend strength)
Volume:                         ├─ Stochastic (Position in range)
  Trading activity              ├─ ROC (Rate of change)
                                ├─ Williams %R
Volatility:                     ├─ CCI (Commodity Channel)
  Price swings                  └─ MFI (Money Flow)

                                [VOLATILITY - 4 features]
                                ├─ ATR (Average True Range)
                                ├─ Bollinger Bands (upper/lower)
                                ├─ Historical volatility
                                └─ Price range

                                [VOLUME - 3 features]
                                ├─ Volume SMA
                                ├─ Volume ratio
                                └─ VWAP

Orderbook:                      [MICROSTRUCTURE - 3 features]
  Bid/ask spread                ├─ Bid-ask spread
  Market depth                  ├─ Depth imbalance
                                └─ Tick direction

                                [STATISTICAL - 2 features]
                                ├─ Skewness
                                └─ Kurtosis

                                ━━━━━━━━━━━━━━━━━━━━━━━━
                                TOTAL: 30 features

                                × 3 TIMEFRAMES (1m, 5m, 15m)
                                ━━━━━━━━━━━━━━━━━━━━━━━━
                                = 90 FEATURES TOTAL
```

---

## 🗄️ Database Schema Visualization

```
POSTGRESQL DATABASE: helios_v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────────────┐
│  TABLE: market_ohlc                                     │
├─────────────────────────────────────────────────────────┤
│  id              BIGSERIAL PRIMARY KEY                  │
│  pair            VARCHAR(20)         = 'BTCZAR'         │
│  timeframe       VARCHAR(10)         = '1m'/'5m'/'15m'  │
│  open_time       TIMESTAMP           = 2025-10-01 13:18 │
│  close_time      TIMESTAMP           = 2025-10-01 13:19 │
│  open_price      NUMERIC(20,8)       = 2019153.00       │
│  high_price      NUMERIC(20,8)       = 2019200.00       │
│  low_price       NUMERIC(20,8)       = 2019100.00       │
│  close_price     NUMERIC(20,8)       = 2019153.00       │
│  volume          NUMERIC(20,8)       = 1.025            │
│  num_trades      INTEGER             = 83               │
│  created_at      TIMESTAMP           = NOW()            │
├─────────────────────────────────────────────────────────┤
│  UNIQUE (pair, timeframe, open_time)                    │
│  INDEX idx_ohlc_pair_tf_open (pair, timeframe, time)    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TABLE: engineered_features                             │
├─────────────────────────────────────────────────────────┤
│  id              BIGSERIAL PRIMARY KEY                  │
│  pair            VARCHAR(20)         = 'BTCZAR'         │
│  features_vector JSONB               = {features: [...90 numbers], feature_names: [...]} │
│  computed_at     TIMESTAMP           = 2025-10-01 13:18 │
├─────────────────────────────────────────────────────────┤
│  INDEX idx_features_pair_computed (pair, computed_at DESC) │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TABLE: market_trades (optional - high volume)          │
├─────────────────────────────────────────────────────────┤
│  id              BIGSERIAL PRIMARY KEY                  │
│  pair            VARCHAR(20)         = 'BTCZAR'         │
│  side            VARCHAR(10)         = 'BUY'/'SELL'     │
│  price           NUMERIC(20,8)       = 2019153.00       │
│  quantity        NUMERIC(20,8)       = 0.001            │
│  executed_at     TIMESTAMP           = 13:18:00.123     │
└─────────────────────────────────────────────────────────┘

EXAMPLE QUERY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SELECT pair, timeframe, open_time, close_price, num_trades
FROM market_ohlc
WHERE pair = 'BTCZAR'
  AND timeframe = '1m'
  AND open_time >= NOW() - INTERVAL '1 hour'
ORDER BY open_time DESC;

RESULT:
┌────────┬───────────┬─────────────────────┬──────────────┬────────────┐
│ pair   │ timeframe │ open_time           │ close_price  │ num_trades │
├────────┼───────────┼─────────────────────┼──────────────┼────────────┤
│ BTCZAR │ 1m        │ 2025-10-01 13:19:00 │ 2018952.00  │ 574        │
│ BTCZAR │ 1m        │ 2025-10-01 13:18:00 │ 2019153.00  │ 83         │
│ BTCZAR │ 1m        │ 2025-10-01 13:17:00 │ 2018672.00  │ 555        │
└────────┴───────────┴─────────────────────┴──────────────┴────────────┘
```

---

## 🎯 Summary: What You See in Action

When you run `test_tier1_with_database.py`, here's the flow:

```
STEP 1: INITIALIZATION (2 seconds)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[INIT] Initializing DatabaseWriter...
[OK] DatabaseWriter ready
                    ↓
        PostgreSQL connected ✓

[INIT] Creating MultiTimeframeAggregator...
[OK] Aggregator ready
                    ↓
        Ready to create 1m, 5m, 15m candles ✓

[INIT] Creating VALR WebSocket client...
[OK] WebSocket client ready
                    ↓
        Connected to wss://api.valr.com/ws/trade ✓


STEP 2: DATA COLLECTION (120 seconds)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[PROGRESS] Trades: 50, Candles: 0
                    ↓
        Collecting trades... (83 total in 1 minute)

[CANDLE] BTCZAR 1m @ 13:18:00 -> DATABASE
                    ↓
        First 1-minute candle created! ✓
        Saved to PostgreSQL ✓

[PROGRESS] Trades: 100, Candles: 1
[PROGRESS] Trades: 150, Candles: 1
                    ↓
        More trades streaming in...

[CANDLE] BTCZAR 1m @ 13:19:00 -> DATABASE
                    ↓
        Second 1-minute candle ✓

... (continues for 2 minutes)

[CANDLE] BTCZAR 5m @ 13:15:00 -> DATABASE
                    ↓
        First 5-minute candle (combines 5× 1m) ✓


STEP 3: VERIFICATION (5 seconds)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[OK] WebSocket: 12,332 messages ✓
[OK] Trades: 1,142 processed ✓
[OK] Candles: 6 created ✓
[OK] Database: 5/5 writes successful ✓
[OK] Features: 540 vectors calculated ✓


STEP 4: DATABASE QUERY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Querying recent candles...
                    ↓
┌────────┬───────────┬─────────────────────┬──────────────┐
│ pair   │ timeframe │ open_time           │ close_price  │
├────────┼───────────┼─────────────────────┼──────────────┤
│ BTCZAR │ 1m        │ 2025-10-01 13:19:00 │ 2018952.00  │
│ BTCZAR │ 1m        │ 2025-10-01 13:18:00 │ 2019153.00  │
│ BTCZAR │ 5m        │ 2025-10-01 13:15:00 │ 2018952.00  │
└────────┴───────────┴─────────────────────┴──────────────┘

[OK] TIER 1 COMPLETE - ALL TESTS PASSED ✓
```

---

**Now you can SEE exactly what Tier 1 does!** 🎉

Try it yourself:
```bash
cd tests/tier1
python test_tier1_with_database.py
```

Watch the magic happen in real-time! ✨
