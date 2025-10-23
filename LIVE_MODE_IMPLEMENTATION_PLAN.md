# LIVE MODE IMPLEMENTATION PLAN

**Status**: 🟡 PLANNING PHASE
**Current Mode**: PAPER (Safe - No Real Money)
**Target Mode**: LIVE (Real VALR Trading)

---

## ⚠️ CRITICAL SAFETY REQUIREMENTS

### Before ANY Live Trading:
1. ✅ **PAPER mode must be fully stable** (COMPLETED - R103k, 66.7% win rate)
2. ⏳ **All code changes must be committed to Git**
3. ⏳ **GitHub repository must be set up and synced**
4. ⏳ **Comprehensive testing checklist must be completed**
5. ⏳ **Start with MINIMAL real capital** (R500 - R1,000 maximum)
6. ⏳ **Manual kill-switch must be tested and ready**
7. ⏳ **Real-time monitoring dashboard must be operational**

---

## 🎯 IMPLEMENTATION STRATEGY

### Phase 1: Git/GitHub Setup ✅
- [x] Create .gitignore for sensitive data
- [x] Commit current working PAPER mode
- [ ] Create GitHub repository
- [ ] Push initial commit to GitHub
- [ ] Set up branch protection rules
- [ ] Document git workflow

### Phase 2: Pre-LIVE Audit (Do NOT Skip!)
- [ ] **Code Review**: Review all trading execution code
- [ ] **Risk Limits**: Verify max position size, max portfolio risk
- [ ] **API Keys**: Confirm VALR API keys have correct permissions
- [ ] **Balance Check**: Verify starting VALR account balance
- [ ] **Order Validation**: Test order placement with minimal size
- [ ] **Emergency Stop**: Test trading halt mechanism
- [ ] **Monitoring**: Set up real-time alerts

### Phase 3: LIVE Mode Code Changes
- [ ] Create feature branch: `feature/live-mode-implementation`
- [ ] Update mode orchestrator configuration
- [ ] Add extra validation for LIVE trades
- [ ] Implement trade confirmation logging
- [ ] Add real-time P&L tracking
- [ ] Create LIVE-specific safety checks

### Phase 4: Testing with Minimal Capital
- [ ] Start with R500 - R1,000 ONLY
- [ ] Place 1-2 manual test trades
- [ ] Verify order execution
- [ ] Verify position tracking
- [ ] Verify P&L calculations
- [ ] Test stop-loss execution
- [ ] Test take-profit execution

### Phase 5: Gradual Rollout
- [ ] Run for 24 hours with minimal capital
- [ ] Review all trades and P&L
- [ ] If successful, increase to R5,000
- [ ] Run for 1 week, monitor daily
- [ ] If successful, increase to R10,000
- [ ] Continue gradual increases with monitoring

---

## 🔧 TECHNICAL CHANGES REQUIRED

### 1. Mode Orchestrator (`src/trading/orchestrator/mode_orchestrator.py`)

**Current State**: Routes to paper trading client
**Required Changes**:
```python
# Current (PAPER):
if mode == "LIVE":
    return PaperTradingClient()  # WRONG! Always returns paper client

# Target (LIVE):
if mode == "LIVE":
    return VALRWebSocketTradingClient()  # Real VALR API
    # OR VALRTradingClient() for REST API
elif mode == "PAPER":
    return PaperTradingClient()
```

**Files to Modify**:
- `src/trading/orchestrator/mode_orchestrator.py`
- `src/trading/execution/execution_router.py`

### 2. Configuration (`config/settings.py` & `.env`)

**Environment Variables**:
```bash
# Paper Trading (Current)
TRADING_MODE=PAPER
ENABLE_PAPER_TRADING=True

# Live Trading (Target)
TRADING_MODE=LIVE
ENABLE_PAPER_TRADING=False

# VALR API (Verify permissions!)
VALR_API_KEY=your_live_api_key
VALR_API_SECRET=your_live_api_secret
```

**Safety Limits to Verify**:
```python
# In config/settings.py or .env
MAX_POSITION_SIZE_ZAR=1000  # Start small!
MAX_PORTFOLIO_RISK_PCT=10   # Conservative for live
MAX_DAILY_LOSS_ZAR=500      # Hard stop
MAX_OPEN_POSITIONS=3        # Limit exposure
```

### 3. Safety Gates (`src/trading/orchestrator/live_safety_gates.py`)

**Add Pre-Trade Validation**:
```python
class LiveSafetyGates:
    def validate_trade_before_execution(self, trade):
        # Check 1: Verify mode is intentionally LIVE
        if not self.confirm_live_mode_enabled():
            raise SafetyError("LIVE mode not explicitly enabled")

        # Check 2: Verify trade size within limits
        if trade.size_zar > MAX_POSITION_SIZE_ZAR:
            raise SafetyError(f"Trade size {trade.size_zar} exceeds limit")

        # Check 3: Check daily loss limit
        if self.daily_loss >= MAX_DAILY_LOSS_ZAR:
            raise SafetyError("Daily loss limit reached")

        # Check 4: Verify API connectivity
        if not self.valr_client.is_connected():
            raise SafetyError("VALR API not connected")

        return True
```

### 4. Monitoring & Alerts

**Add Real-Time Monitoring**:
```python
# src/trading/autonomous/trading_engine.py
async def execute_trade_with_monitoring(self, trade):
    # Log BEFORE execution
    logger.critical(f"🔴 LIVE TRADE EXECUTION: {trade}")

    # Execute
    result = await self.execution_router.execute_trade(trade)

    # Log AFTER execution
    logger.critical(f"✅ LIVE TRADE EXECUTED: {result}")

    # Send alert (email/SMS)
    await alert_manager.send_critical_alert(
        title="LIVE TRADE EXECUTED",
        message=f"Pair: {trade.pair}, Side: {trade.side}, Size: R{trade.size_zar}"
    )

    return result
```

---

## 🧪 TESTING CHECKLIST (CRITICAL!)

### Pre-Deployment Tests (PAPER Mode)

#### Test 1: Order Execution Flow
- [ ] Generate BUY signal
- [ ] Verify order creation
- [ ] Verify order submission
- [ ] Verify position tracking
- [ ] Verify P&L calculation

#### Test 2: Stop-Loss Execution
- [ ] Create position with stop-loss
- [ ] Manually trigger stop-loss condition
- [ ] Verify position closes
- [ ] Verify P&L recorded

#### Test 3: Take-Profit Execution
- [ ] Create position with take-profit
- [ ] Manually trigger take-profit condition
- [ ] Verify position closes
- [ ] Verify P&L recorded

#### Test 4: Risk Limits
- [ ] Test max position size limit
- [ ] Test max portfolio risk limit
- [ ] Test max daily loss limit
- [ ] Verify trades are rejected when limits exceeded

#### Test 5: Emergency Stop
- [ ] Trigger emergency stop via dashboard
- [ ] Verify all pending orders cancelled
- [ ] Verify no new trades placed
- [ ] Verify system can be restarted safely

### Post-Deployment Tests (LIVE Mode - Minimal Capital!)

#### Test 6: First LIVE Trade
- [ ] Place 1 BUY order for R200
- [ ] Verify order appears on VALR
- [ ] Verify position tracked in system
- [ ] Verify dashboard shows correct data

#### Test 7: LIVE Stop-Loss
- [ ] Wait for stop-loss to trigger naturally
- [ ] OR manually trigger by adjusting price
- [ ] Verify VALR order executed
- [ ] Verify P&L matches expected

#### Test 8: LIVE P&L Tracking
- [ ] Monitor real-time P&L for 24 hours
- [ ] Compare system P&L to VALR account balance
- [ ] Verify all fees/spreads accounted for
- [ ] Check for any discrepancies

---

## 📋 DEPLOYMENT CHECKLIST

### Pre-Deployment (Complete ALL Before Going LIVE)

#### Code Quality
- [ ] All tests passing in PAPER mode
- [ ] Code committed to git with descriptive message
- [ ] Feature branch created (`feature/live-mode-implementation`)
- [ ] Code reviewed (if possible, get second opinion)
- [ ] No TODO/FIXME comments in critical code paths

#### Configuration
- [ ] `.env` file configured for LIVE mode
- [ ] VALR API keys verified and tested
- [ ] Safety limits configured (max size, max risk, etc.)
- [ ] Starting capital recorded (for P&L tracking)
- [ ] Dashboard pointing to correct server

#### Safety & Monitoring
- [ ] Emergency stop button tested and working
- [ ] Real-time monitoring dashboard operational
- [ ] Alert system configured (email/SMS/Telegram)
- [ ] Logging enabled for all trades
- [ ] Backup kill-switch ready (manual server stop)

#### Risk Management
- [ ] Starting with R500 - R1,000 MAXIMUM
- [ ] Max position size set to R200 - R300
- [ ] Max portfolio risk set to 10% or less
- [ ] Max daily loss set to R500
- [ ] Max open positions set to 3

#### Documentation
- [ ] Current system state documented
- [ ] Expected behavior documented
- [ ] Rollback plan documented
- [ ] Emergency contacts listed
- [ ] Commit hash recorded

### Deployment Steps

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/live-mode-implementation
   ```

2. **Make Code Changes**
   - Update mode orchestrator
   - Add safety gates
   - Add monitoring/logging
   - Update configuration

3. **Test Thoroughly in PAPER Mode**
   - Run full test suite
   - Manual testing of all features
   - Verify no regressions

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: LIVE mode implementation with safety gates"
   git push origin feature/live-mode-implementation
   ```

5. **Deploy to Server**
   ```bash
   # Backup current version
   ssh ubuntu@server "cd /home/ubuntu && cp -r . ../backup_$(date +%Y%m%d_%H%M%S)"

   # Deploy new code
   scp -r src/ ubuntu@server:/home/ubuntu/
   scp main.py ubuntu@server:/home/ubuntu/
   scp .env ubuntu@server:/home/ubuntu/

   # Restart server
   ssh ubuntu@server "pkill -9 python && cd /home/ubuntu && nohup python main.py > server.log 2>&1 &"
   ```

6. **Monitor First Hour**
   - Watch dashboard continuously
   - Check logs every 5 minutes
   - Verify trades execute correctly
   - Be ready to kill switch if needed

### Post-Deployment Monitoring

#### First 24 Hours
- [ ] Check system every hour
- [ ] Review all trades executed
- [ ] Compare system P&L to VALR balance
- [ ] Look for any errors/warnings in logs
- [ ] Verify no unexpected behavior

#### First Week
- [ ] Daily review of all trades
- [ ] Weekly P&L reconciliation with VALR
- [ ] Analyze win rate and profitability
- [ ] Adjust risk limits if needed
- [ ] Document any issues encountered

#### First Month
- [ ] Weekly detailed performance review
- [ ] Compare LIVE vs PAPER performance
- [ ] Adjust strategy based on real results
- [ ] Gradually increase capital if profitable
- [ ] Document lessons learned

---

## 🚨 EMERGENCY PROCEDURES

### Kill Switch Activation

**Method 1: Dashboard Emergency Stop**
1. Open dashboard: http://your-server-ip/dashboard.html
2. Click "EMERGENCY STOP" button
3. Verify all trading halted
4. Check no new orders being placed

**Method 2: Manual Server Stop**
```bash
ssh ubuntu@server
pkill -9 python
# Verify no Python processes running
ps aux | grep python
```

**Method 3: API Key Revocation**
1. Log into VALR account
2. Revoke API key immediately
3. System will fail to place new orders
4. Existing orders may need manual cancellation

### Rollback to PAPER Mode

```bash
# SSH to server
ssh ubuntu@server "cd /home/ubuntu"

# Update .env to PAPER mode
echo "TRADING_MODE=PAPER" > .env
echo "ENABLE_PAPER_TRADING=True" >> .env

# Restart server
pkill -9 python
nohup python main.py > server.log 2>&1 &

# Verify mode
curl http://localhost:8100/api/mode/current
```

### Rollback to Previous Version

```bash
# Restore from backup
ssh ubuntu@server "cd /home/ubuntu && rm -rf src/ && cp -r ../backup_YYYYMMDD_HHMMSS/* ."

# Restart
ssh ubuntu@server "pkill -9 python && cd /home/ubuntu && nohup python main.py > server.log 2>&1 &"
```

---

## 📊 SUCCESS METRICS

### Minimum Requirements for LIVE Mode Success

**Week 1** (R500 - R1,000 capital):
- No system crashes or errors
- All trades execute correctly
- P&L tracking accurate
- Win rate >= 60%
- Max drawdown <= 10%

**Week 2-4** (R5,000 capital):
- Consistent profitability
- Win rate >= 60%
- Average trade P&L positive
- No major bugs or issues
- Max drawdown <= 15%

**Month 2+** (R10,000+ capital):
- Monthly profitability
- Win rate >= 55%
- Sharpe ratio >= 1.0
- Max drawdown <= 20%
- System reliability >= 99%

### Red Flags (Stop LIVE Trading Immediately)

- ❌ Win rate drops below 40%
- ❌ 3+ consecutive losing days
- ❌ Daily loss exceeds R500
- ❌ System crashes or errors
- ❌ Orders not executing correctly
- ❌ P&L discrepancies with VALR
- ❌ Unexpected behavior of any kind

---

## 🔄 GIT WORKFLOW

### Branch Strategy

**Main Branches**:
- `master` - Stable PAPER mode (current)
- `production` - Stable LIVE mode (future)

**Feature Branches**:
- `feature/live-mode-implementation` - LIVE mode development
- `feature/new-strategy` - Strategy improvements
- `bugfix/xyz` - Bug fixes

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Testing
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance

**Examples**:
```bash
feat(trading): Implement LIVE mode with safety gates
fix(portfolio): Correct P&L calculation for closed trades
docs(readme): Add LIVE mode deployment instructions
```

### Before Every Commit

```bash
# 1. Check status
git status

# 2. Review changes
git diff

# 3. Run tests (if available)
pytest tests/

# 4. Stage changes
git add <files>

# 5. Commit with descriptive message
git commit -m "feat(scope): description"

# 6. Push to remote
git push origin <branch-name>
```

---

## 📝 NEXT STEPS

1. **Set up GitHub repository**
   - Create new repo: `helios-trading-v3`
   - Push initial commit
   - Set up branch protection

2. **Create feature branch for LIVE mode**
   ```bash
   git checkout -b feature/live-mode-implementation
   ```

3. **Complete testing checklist in PAPER mode**
   - Go through every test
   - Document results
   - Fix any issues found

4. **Review and modify code for LIVE mode**
   - Update mode orchestrator
   - Add safety gates
   - Add monitoring

5. **Test with minimal capital (R500)**
   - Deploy to test environment
   - Run for 24 hours
   - Monitor continuously

6. **Gradual rollout**
   - Week 1: R500
   - Week 2: R1,000
   - Month 2: R5,000
   - Month 3+: Scale if profitable

---

## ⚠️ FINAL WARNING

**LIVE mode means REAL MONEY is at risk!**

- Start small (R500 max)
- Monitor constantly
- Be ready to shut down
- Don't rush the process
- Paper profits ≠ Live profits
- Test everything twice
- When in doubt, stay in PAPER mode

**Remember**: It's better to miss profits than to lose capital through untested code.

---

**Document Version**: 1.0
**Date**: October 23, 2025
**Author**: System
**Status**: Planning Phase
