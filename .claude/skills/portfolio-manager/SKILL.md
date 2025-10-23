# Portfolio Manager - The Final Guardian

## Description
Critical knowledge about Helios Tier 5 Portfolio Manager - the system that controls trade execution, risk limits, and position management. This is THE component that determines success or failure. Activates when discussing trades, positions, risk limits, or portfolio operations.

**Use this when**: Making trade decisions, modifying risk limits, debugging position issues, or understanding why trades are approved/rejected.

---

## Why Portfolio Manager is Most Important

### The Reality
```
Tiers 1-4 can be PERFECT, but if Portfolio Manager fails:
→ Bad position sizing = account blown
→ Risk limits ignored = catastrophic losses
→ Position tracking broken = unknown exposure
→ Order execution fails = no trading

Portfolio Manager is the ONLY tier that:
- Touches real money
- Executes real orders
- Enforces risk limits
- Prevents catastrophic losses
```

### What It Does
```
INPUT:  ML prediction (BUY/SELL), LLM approval, trade parameters
OUTPUT: Executed trade OR rejection with detailed reason

Responsibilities:
1. Check 7 institutional risk limits (the guardian)
2. Calculate optimal position sizes (MPT + Black-Litterman)
3. Execute orders via VALR (real money movement)
4. Track position lifecycle (open → monitor → close)
5. Monitor P&L and trigger stops
6. Emergency halt when needed
```

---

## 3 Core Components

### 1. Portfolio Risk Manager (`src/portfolio/risk/portfolio_risk_manager.py`)

**Purpose**: Final guardian - checks 7 risk limits before ANY trade

**The 7 Critical Risk Checks**:
```python
CHECK 1: Portfolio Drawdown Limit
- Current: -15% max drawdown (hard stop)
- Fails if: Current drawdown > 15%
- Purpose: Prevent catastrophic portfolio losses

CHECK 2: Daily Loss Limit
- Current: -5% daily loss limit
- Fails if: Today's loss > 5%
- Purpose: Stop bleeding before it's fatal

CHECK 3: Dynamic Position Capacity (RISK-BASED, NOT COUNT)
- Current: Max 15% portfolio risk exposure
- Fails if: Adding trade exceeds risk budget
- Purpose: Volatility-targeting (Moreira & Muir 2017)
- NOTE: NOT a hardcoded "max 5 positions" limit

CHECK 4: Single Position Size
- Current: Max 20% per position
- Fails if: Position > 20% of portfolio
- Purpose: Prevent concentration risk

CHECK 5: Sector Exposure
- Current: Max 60% in one sector
- Fails if: Crypto exposure > 60%
- Purpose: Diversification (all crypto = one sector)

CHECK 6: Correlation Exposure
- Current: Don't add if correlation > 0.90
- Fails if: New position too correlated with existing
- Purpose: True diversification (low correlation)

CHECK 7: Portfolio Leverage
- Current: Max 3.0x leverage
- Fails if: Total leverage > 3x
- Purpose: Prevent over-leveraging
```

**Risk Limits (Current Configuration)**:
```python
class PortfolioRiskLimits:
    max_drawdown_pct: 0.15              # -15% max drawdown
    max_single_position_pct: 0.20       # 20% max per position
    max_sector_exposure_pct: 0.60       # 60% max in one sector
    max_correlation_threshold: 0.90     # Don't add if corr > 0.90
    daily_loss_limit_pct: 0.05          # -5% daily loss
    max_leverage: 3.0                   # 3x max leverage

    # Dynamic capacity (NOT hardcoded position count)
    max_portfolio_risk_exposure_pct: 0.15  # Max 15% at risk
    min_position_size_pct: 0.05            # Min 5% position
```

**How to Check if Trade Will Pass**:
```python
# Before trade execution
result = await portfolio_risk_manager.check_trade_risk(
    pair='BTCZAR',
    signal='BUY',
    trade_params={
        'position_size_zar': 10000.0,
        'leverage': 1.5,
        'stop_loss_pct': 0.02
    }
)

if result.passed:
    # All 7 checks passed - safe to trade
    logger.info("Trade approved")
else:
    # Failed checks
    logger.warning(f"Trade rejected: {result.reason}")
    logger.warning(f"Violated limits: {result.violated_limits}")
```

---

### 2. Position Manager (`src/portfolio/positions/position_manager.py`)

**Purpose**: Manage position lifecycle from open to close

**Position Lifecycle**:
```
1. OPEN
   → Execute market order via VALR
   → Record in database
   → Set stop loss and take profit levels
   → Track entry price

2. MONITOR (continuous)
   → Track current P&L (unrealized)
   → Check if stop loss hit
   → Check if take profit hit
   → Check if timeout reached (max holding period)
   → Update trailing stops

3. CLOSE
   → Execute closing order via VALR
   → Record realized P&L
   → Update position status
   → Archive position data
```

**Position Status Values**:
```python
OPEN            # Active position
CLOSED          # Manually closed
STOPPED_OUT     # Hit stop loss
TAKE_PROFIT     # Hit take profit
TIMEOUT         # Max holding period exceeded
EMERGENCY_CLOSE # Emergency stop triggered
```

**Opening a Position**:
```python
result = await position_manager.open_position(
    pair='BTCZAR',
    signal='BUY',
    trade_params={
        'position_size_zar': 10000.0,
        'leverage': 1.5,
        'stop_loss_pct': 0.02,      # -2% stop loss
        'take_profit_pct': 0.06     # +6% take profit
    },
    strategic_reasoning="LLM approved: Strong bullish momentum"
)

if result['success']:
    position_id = result['position_id']
    entry_price = result['entry_price']
```

**Monitoring Positions**:
```python
# Get all open positions
positions = await position_manager.get_open_positions()

for position in positions:
    # Check P&L
    current_pnl = position.unrealized_pnl

    # Check if stop loss hit
    if current_pnl_pct <= -position.stop_loss_pct:
        await position_manager.close_position(
            position_id=position.id,
            reason="STOPPED_OUT"
        )
```

**Closing a Position**:
```python
result = await position_manager.close_position(
    position_id=123,
    reason="TAKE_PROFIT"  # or STOPPED_OUT, TIMEOUT, EMERGENCY_CLOSE
)

if result['success']:
    realized_pnl = result['realized_pnl']
    logger.info(f"Closed position {position_id}: P&L = R{realized_pnl:,.2f}")
```

---

### 3. MPT Optimizer (`src/portfolio/optimization/mpt_optimizer.py`)

**Purpose**: Calculate optimal portfolio weights using Modern Portfolio Theory + Black-Litterman

**The Black-Litterman Process** (5 Steps):
```
Step 1: Calculate Covariance Matrix
→ Historical returns for all pairs
→ Covariance matrix shows how pairs move together
→ Used to estimate portfolio risk

Step 2: Get Market Cap Weights (Prior)
→ Use market cap as equilibrium weights
→ E.g., BTC 60%, ETH 30%, SOL 10%
→ This is the "market consensus"

Step 3: Implied Equilibrium Returns
→ Reverse optimization: What returns justify market weights?
→ Uses risk aversion coefficient (λ = 2.5)
→ Formula: π = λ * Σ * w_market

Step 4: Incorporate ML Views (Black-Litterman)
→ Combine market prior with ML predictions
→ Weight by confidence scores
→ Formula: E[R] = [(τΣ)^-1 + P'Ω^-1P]^-1 [(τΣ)^-1π + P'Ω^-1Q]
→ Higher confidence = more weight to ML view

Step 5: Optimize for Max Sharpe Ratio
→ Maximize: (E[R] - r_f) / σ
→ Subject to: weights sum to 1, all weights ≥ 0
→ Result: Optimal allocation across pairs
```

**Using MPT Optimizer**:
```python
# ML predictions from Tier 2
ml_predictions = {
    'BTCZAR': 0.05,   # +5% expected return
    'ETHZAR': 0.03,   # +3% expected return
    'SOLZAR': 0.08    # +8% expected return
}

# Confidence from Tier 2
confidence_scores = {
    'BTCZAR': 0.85,   # 85% confident
    'ETHZAR': 0.75,   # 75% confident
    'SOLZAR': 0.90    # 90% confident
}

# Calculate optimal weights
optimal_weights = await mpt_optimizer.calculate_optimal_weights(
    pairs=['BTCZAR', 'ETHZAR', 'SOLZAR'],
    ml_predictions=ml_predictions,
    confidence_scores=confidence_scores
)

# Result: {'BTCZAR': 0.35, 'ETHZAR': 0.25, 'SOLZAR': 0.40}
# Interpretation: 35% BTC, 25% ETH, 40% SOL for max Sharpe ratio
```

**When NOT to Use MPT**:
```
❌ Single-pair trading (just trade one pair)
❌ < 30 days historical data (not enough for covariance)
❌ Highly correlated pairs (correlation > 0.95 = no diversification benefit)

✅ Multi-pair trading (3+ pairs)
✅ Sufficient historical data (60+ days)
✅ Moderate correlation (0.3-0.8 ideal)
```

---

## File Locations

```
Portfolio Manager Components:
├── src/portfolio/risk/portfolio_risk_manager.py      # 7 risk checks
├── src/portfolio/positions/position_manager.py       # Position lifecycle
├── src/portfolio/optimization/mpt_optimizer.py       # MPT + Black-Litterman
└── src/api/routers/portfolio.py                      # API endpoints

Configuration:
├── config/risk_config.py                             # Risk limits config
└── .env                                              # TRADING_MODE=PAPER/LIVE

Database Tables:
├── positions                                         # Open/closed positions
├── portfolio_state                                   # Current portfolio metrics
└── portfolio_snapshots                               # Historical portfolio values
```

---

## API Endpoints

### Portfolio Summary
```bash
GET /api/portfolio/summary
# Returns: total_value, pnl, win_rate, sharpe, drawdown

GET /api/portfolio/state/current
# Returns: detailed portfolio state (positions, cash, exposure)

GET /api/portfolio/performance/metrics
# Returns: performance analytics (Sharpe, Sortino, max DD, etc.)
```

### Positions
```bash
GET /api/portfolio/positions
# Returns: All positions (open + closed)

GET /api/portfolio/positions?status=OPEN
# Returns: Only open positions

GET /api/portfolio/positions/{position_id}
# Returns: Specific position details

POST /api/portfolio/positions/{position_id}/close
# Closes position manually
```

### Risk Metrics
```bash
GET /api/portfolio/risk-metrics
# Returns: Current risk metrics (drawdown, leverage, exposure, etc.)

GET /api/portfolio/risk/limits
# Returns: Current risk limits configuration

PUT /api/portfolio/risk/limits
# Updates risk limits (DANGEROUS - use carefully)
```

---

## Critical Configuration

### Risk Limits (config/risk_config.py)
```python
PORTFOLIO_RISK_LIMITS = {
    'max_drawdown_pct': 0.15,           # -15% max DD
    'max_single_position_pct': 0.20,    # 20% max position
    'max_sector_exposure_pct': 0.60,    # 60% max sector
    'max_correlation_threshold': 0.90,  # Don't add if corr > 0.90
    'daily_loss_limit_pct': 0.05,       # -5% daily loss
    'max_leverage': 3.0,                # 3x max leverage
    'max_portfolio_risk_exposure_pct': 0.15,  # 15% max risk
    'min_position_size_pct': 0.05       # 5% min position
}
```

### Position Defaults
```python
DEFAULT_STOP_LOSS_PCT = 0.02       # -2% stop loss
DEFAULT_TAKE_PROFIT_PCT = 0.06     # +6% take profit (3:1 reward/risk)
MAX_POSITION_HOLDING_HOURS = 72    # 3 days max holding
```

---

## Common Issues and Solutions

### Issue 1: "Trade rejected - drawdown limit exceeded"
**Cause**: Portfolio drawdown > 15%
**Solution**:
- Stop trading until drawdown recovers
- Review losing trades
- Reduce position sizes
- Tighten stop losses

### Issue 2: "Trade rejected - position capacity full"
**Cause**: Adding trade would exceed 15% portfolio risk exposure
**Solution**:
- NOT a position count issue (it's risk-based)
- Close existing positions to free risk capacity
- OR reduce new position size
- OR wait for volatility to decrease (reduces risk per position)

### Issue 3: "Position not closing at stop loss"
**Cause**: Stop loss monitoring not running
**Solution**:
- Check autonomous engine is running
- Check position monitoring loop active
- Verify WebSocket price updates working

### Issue 4: "Orders executing in paper mode when LIVE mode expected"
**Cause**: Trading mode mismatch
**Solution**:
```bash
# Check current mode
curl http://localhost:8000/api/orchestrator/system/trading/mode

# Set to LIVE (DANGEROUS - only with small capital first!)
curl -X PUT http://localhost:8000/api/orchestrator/system/trading/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "LIVE"}'
```

### Issue 5: "MPT optimizer returning equal weights"
**Cause**: Insufficient historical data or numerical instability
**Solution**:
- Need 60+ days of price data
- Check covariance matrix is invertible
- Increase regularization if numerical issues
- Fallback to equal weights if optimization fails

---

## Trading Mode: PAPER vs LIVE

### PAPER Mode (Safe - Default)
```
✅ Simulated order execution
✅ Fake fills at market price
✅ No real money risk
✅ Full position tracking
✅ All risk checks still run
✅ Perfect for testing

Use for:
- Testing new strategies
- Validating risk limits
- Learning system behavior
- Proving 7-day stability
```

### LIVE Mode (Real Money - DANGEROUS)
```
⚠️ Real VALR API orders
⚠️ Real money at risk
⚠️ Real fees paid
⚠️ Cannot undo trades
⚠️ Must have VALR client implemented

Before going LIVE:
1. 7-day paper test passed?
2. VALR client implemented and tested on testnet?
3. API keys securely stored?
4. Starting with SMALL capital (R1,000-5,000)?
5. Monitoring VERY closely?

IF ANY IS NO → STAY IN PAPER MODE
```

### Switching Modes
```python
# Via API
PUT /api/orchestrator/system/trading/mode
Body: {"mode": "LIVE"}  # or "PAPER"

# Via environment variable
TRADING_MODE=PAPER  # in .env file

# Check current mode before ANY trade
mode = await get_trading_mode()
if mode == "LIVE":
    logger.warning("⚠️ LIVE MODE - REAL MONEY AT RISK")
```

---

## Position Sizing Example

### Scenario: BTCZAR Buy Signal
```
Portfolio Value: R100,000
Signal: BUY BTCZAR
ML Confidence: 85%
GARCH Volatility: 4% daily
```

### Tier 3 (Risk) Calculates:
```python
# Kelly Criterion (0.25 fractional)
win_prob = 0.85
win_loss_ratio = 3.0  # 3:1 reward/risk
kelly_pct = (win_prob * win_loss_ratio - (1 - win_prob)) / win_loss_ratio
kelly_pct = 0.23  # 23% full Kelly

fractional_kelly = kelly_pct * 0.25  # 25% fractional
fractional_kelly = 0.0575  # 5.75%

# Volatility scaling
vol_target = 0.10  # 10% annual vol target
vol_current = 0.04 * sqrt(252) = 0.635  # 63.5% annual
vol_scalar = vol_target / vol_current = 0.157

# Position size = Kelly * Vol scalar * Portfolio
position_size = 0.0575 * 0.157 * 100000 = R903
```

### Tier 5 (Portfolio) Checks:
```python
CHECK 1: Drawdown? Currently -2% < -15% ✅ PASS
CHECK 2: Daily loss? Currently -1% < -5% ✅ PASS
CHECK 3: Risk capacity? R903 @ 4% vol = R36 risk
         Current risk: R450
         Max risk: R15,000 (15% of R100k)
         New total: R486 < R15,000 ✅ PASS
CHECK 4: Position size? R903 / R100k = 0.9% < 20% ✅ PASS
CHECK 5: Sector exposure? Crypto = 30% + 0.9% = 30.9% < 60% ✅ PASS
CHECK 6: Correlation? BTC correlation to portfolio = 0.75 < 0.90 ✅ PASS
CHECK 7: Leverage? Current 1.2x + 0.01x = 1.21x < 3.0x ✅ PASS

RESULT: ALL CHECKS PASSED → EXECUTE TRADE
```

### Execution:
```python
await position_manager.open_position(
    pair='BTCZAR',
    signal='BUY',
    trade_params={
        'position_size_zar': 903.0,
        'leverage': 1.0,
        'stop_loss_pct': 0.02,      # -2% = R18 max loss
        'take_profit_pct': 0.06     # +6% = R54 gain
    },
    strategic_reasoning="Kelly + Vol targeting, LLM approved"
)

# Position opened:
# Entry: R1,200,000 BTC price
# Quantity: 0.0007525 BTC
# Stop loss: R1,176,000 (-2%)
# Take profit: R1,272,000 (+6%)
# Max loss: R18
# Max gain: R54
# Risk/Reward: 1:3 ✅
```

---

## Emergency Procedures

### Emergency Stop (Manual)
```bash
# Stop all trading immediately
POST /api/autonomous-engine/emergency-stop

# Close all positions
POST /api/portfolio/positions/close-all

# Set mode to PAPER
PUT /api/orchestrator/system/trading/mode
Body: {"mode": "PAPER"}
```

### Automatic Emergency Stops
```
System auto-stops if:
❌ Drawdown > 15% (risk limit breach)
❌ Daily loss > 5% (risk limit breach)
❌ WebSocket disconnected > 1 hour (no price data)
❌ Database connection lost (can't track positions)
❌ VALR API errors > 10 in 1 minute (execution issues)

Action: Emergency close all positions, halt trading
```

---

## Success Criteria

### Portfolio Manager Working Correctly If:
```
✅ All 7 risk checks running correctly
✅ Positions open and close as expected
✅ Stop losses trigger correctly
✅ Take profits execute correctly
✅ Risk limits enforced (no violations)
✅ P&L tracking accurate
✅ Portfolio value calculated correctly
✅ Emergency stops work when triggered
✅ Paper mode executes simulated trades
✅ Live mode executes real trades (when VALR client ready)
```

### Portfolio Manager Failing If:
```
❌ Risk checks passing when they should fail
❌ Risk checks failing when they should pass
❌ Positions not opening (order execution broken)
❌ Stop losses not triggering (monitoring broken)
❌ P&L calculations wrong
❌ Positions tracked incorrectly
❌ Emergency stop not working
❌ Trading in wrong mode (PAPER vs LIVE mismatch)
```

---

## Key Metrics to Monitor

### Daily Checks
```
Portfolio Value:          Track total value trend
Daily P&L:               Monitor for -5% limit
Open Positions:          Count and exposure
Current Drawdown:        Monitor for -15% limit
Win Rate:                Track (but no arbitrary target)
Average Position Size:   Should vary with volatility
```

### Weekly Checks
```
Risk Limit Violations:   Should be ZERO
Stop Loss Hit Rate:      Track (risk management working?)
Take Profit Hit Rate:    Track (targets realistic?)
Position Timeout Rate:   Track (holding too long?)
Emergency Stops:         Should be rare (system stable?)
```

---

## Remember

**Portfolio Manager is the final guardian.**

Everything else can work perfectly:
- Data ingestion ✅
- ML predictions ✅
- Risk calculations ✅
- LLM approvals ✅

But if Portfolio Manager fails:
- Bad position sizing → Account blown
- Risk limits ignored → Catastrophic losses
- Execution broken → No trading
- Monitoring broken → Unknown exposure

**This is THE component that touches real money. It MUST work correctly.**

**If it works correctly:**
- Risk is managed
- Positions are sized properly
- Stops protect capital
- System can trade profitably

**Focus on getting this right before everything else.**

---

## Testing Portfolio Manager

### Unit Tests
```bash
pytest tests/portfolio/test_risk_manager.py -v
pytest tests/portfolio/test_position_manager.py -v
pytest tests/portfolio/test_mpt_optimizer.py -v
```

### Integration Tests
```bash
# Test full trade flow
pytest tests/integration/test_trade_execution.py -v

# Test risk limit enforcement
pytest tests/integration/test_risk_limits.py -v
```

### Manual Testing (PAPER Mode)
```python
# 1. Start server
python main.py

# 2. Start autonomous engine in PAPER mode
POST /api/autonomous-engine/start

# 3. Monitor for trades
GET /api/portfolio/positions

# 4. Verify risk checks
GET /api/portfolio/risk-metrics

# 5. Test emergency stop
POST /api/autonomous-engine/emergency-stop
```

---

## Summary

**Portfolio Manager = The Final Guardian**

**3 Components**:
1. Risk Manager - 7 checks before every trade
2. Position Manager - Lifecycle from open to close
3. MPT Optimizer - Optimal allocation across pairs

**Critical Files**:
- `src/portfolio/risk/portfolio_risk_manager.py`
- `src/portfolio/positions/position_manager.py`
- `src/portfolio/optimization/mpt_optimizer.py`

**Why It's Most Important**:
- Only component that touches real money
- Enforces all risk limits
- Executes all trades
- Prevents catastrophic losses

**If this breaks, everything breaks.**
**If this works, system can be profitable.**

**Get this right. Everything else is secondary.**
