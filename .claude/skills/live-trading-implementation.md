# Live Trading Implementation Skill

## Purpose
Guide the implementation of PAPER → LIVE trading mode switching for Helios V3.0 trading system with safety-first approach.

## When to Use
- When implementing trading mode orchestrator integration
- When enabling LIVE trading capabilities
- When switching between PAPER and LIVE modes
- When testing real money trading features

## Prerequisites
1. ✅ System backup completed
2. ✅ VALR credentials configured (may have zero balance for testing)
3. ✅ Paper trading working correctly
4. ✅ User confirmation at each phase

## Implementation Phases

### Phase 1: API Persistence (2 hours)
**Goal:** Make trading mode persist across API restarts

**Tasks:**
1. Replace global `_current_mode` variable with database queries
2. Update `POST /api/trading/mode` endpoint
3. Update `GET /api/trading/mode` endpoint
4. Add startup mode loading from database
5. Test mode persistence across restarts

**Files to Modify:**
- `src/api/routers/trading.py` (mode endpoints)
- `main.py` (startup sequence)

**Testing:**
- Set mode to LIVE via API
- Restart API server
- Verify mode is still LIVE
- Verify database `trading_mode_state` table updated

**Success Criteria:**
- Mode persists across restarts
- Database audit trail working
- No errors in API responses

**User Checkpoint:** ✋ STOP - Await user review and approval

---

### Phase 2: Execution Routing (3 hours)
**Goal:** Ensure correct trading client used at execution time

**Tasks:**
1. Create `ExecutionRouter` class
2. Implement dynamic mode checking
3. Update trading engine to query mode before trades
4. Allow hot-swapping between paper/live clients
5. Add mode verification in trade execution

**New Files:**
- `src/trading/execution/execution_router.py`

**Files to Modify:**
- `src/trading/autonomous/trading_engine.py` (trade execution)

**Testing:**
- Start in PAPER mode
- Switch to LIVE mode via API
- Verify next trade attempt uses LIVE client
- Switch back to PAPER
- Verify uses paper client again

**Expected Errors:**
- "Insufficient funds" when LIVE client attempts trade (NORMAL - account has zero balance)

**Success Criteria:**
- Mode switches affect trade execution
- No cached client issues
- Proper error handling for insufficient funds

**User Checkpoint:** ✋ STOP - Await user review and approval

---

### Phase 3: LIVE Safety Gates (4 hours)
**Goal:** Prevent dangerous mode switches

**Tasks:**
1. Pre-switch validation:
   - Check all positions closed
   - Check no pending orders
   - Test VALR credentials
   - Verify risk configuration complete
2. Add confirmation requirements for LIVE mode
3. Implement rollback on validation failure
4. Add detailed error messages

**Files to Modify:**
- `src/trading/orchestrator/mode_orchestrator.py`

**Testing:**
- Try switching to LIVE with open positions (should REJECT)
- Try switching to LIVE with pending orders (should REJECT)
- Try switching with invalid credentials (should REJECT)
- Try switching with all validations passed (should SUCCEED with confirmation)

**Success Criteria:**
- Cannot switch to LIVE with open positions
- Cannot switch to LIVE with pending orders
- Detailed validation error messages
- Confirmation required for LIVE mode

**User Checkpoint:** ✋ STOP - Await user review and approval

---

### Phase 4: LIVE Enforcement (5 hours)
**Goal:** Enforce risk limits in LIVE mode

**Tasks:**
1. Position size enforcement:
   - Max 20% per position
   - Check before order placement
2. Leverage checking:
   - Max 3x leverage
   - Reject orders exceeding limit
3. Daily loss monitoring:
   - Track P&L daily
   - Auto-stop at 5% daily loss
4. Drawdown circuit breaker:
   - Track max drawdown
   - Emergency stop at 15%
5. Email/webhook notifications for LIVE trades

**New Files:**
- `src/risk/live_enforcement.py`

**Files to Modify:**
- `src/risk/position_sizing/kelly_calculator.py`
- `src/trading/autonomous/trading_engine.py`

**Testing:**
- Test position size capping (attempt 25%, verify capped to 20%)
- Test leverage rejection (attempt 4x, verify rejected)
- Test daily loss monitoring (simulate 5% loss, verify auto-stop)
- Test drawdown circuit breaker (simulate 15% drawdown, verify emergency stop)
- Verify notifications sent

**Success Criteria:**
- All risk limits enforced
- Auto-stop mechanisms working
- Notifications sent for LIVE trades
- Cannot exceed limits even with explicit orders

**User Checkpoint:** ✋ STOP - Await user review and approval

---

### Phase 5: LIVE Mode Activation (1 hour)
**Goal:** Test with real VALR account balance

**Prerequisites:**
- ✅ All 4 phases complete
- ✅ All tests passing
- 💰 **USER ACTION REQUIRED: Add funds to VALR account**

**Tasks:**
1. User adds funds to VALR account
2. Test small LIVE trade (minimum size)
3. Verify order placement works
4. Verify execution reporting
5. Verify P&L tracking
6. Verify notifications

**Testing:**
- Place minimum size market order
- Verify appears in VALR account
- Verify tracked in database
- Verify P&L calculated
- Verify risk limits respected

**Success Criteria:**
- Real trade executes successfully
- Appears in VALR UI
- Tracked in Helios database
- All safety mechanisms active

**Final Checkpoint:** ✅ LIVE trading operational

---

## Safety Rules (MANDATORY)

### Before ANY Implementation:
1. ✅ Complete system backup
2. ✅ Create rollback documentation
3. ✅ User approval to proceed

### During Implementation:
1. ⚠️ Test each phase completely before proceeding
2. ⚠️ STOP after each phase for user review
3. ⚠️ Document all changes made
4. ⚠️ Keep backup accessible

### During Testing:
1. ✅ "Insufficient funds" errors are EXPECTED (zero balance)
2. ✅ PAPER mode is always safe to test
3. ✅ LIVE mode testing requires user confirmation
4. ⚠️ Never skip validation checks

### Before LIVE Trading:
1. 💰 User MUST add funds to VALR account
2. ✅ All 4 phases tested and approved
3. ✅ User explicit approval for real trading
4. ✅ Start with minimum trade size

---

## Rollback Procedure

### If Issues Occur:
1. **Emergency Stop:**
   ```bash
   curl -X POST http://localhost:8100/api/trading/emergency-stop
   ```

2. **Restore from Backup:**
   ```bash
   # Local
   cd C:\Jupyter\New_Valr
   rm -rf src config main.py
   cp -r backups_before_live_trading/local_backup_*/  .

   # AWS
   ssh -i Main.pem ubuntu@13.61.17.19 "cd /home/ubuntu && tar -xzf backups_before_live_trading/aws_backup_*.tar.gz"
   ```

3. **Reset Database Mode:**
   ```sql
   UPDATE trading_mode_state SET current_mode = 'PAPER' WHERE id = 1;
   ```

4. **Restart Services:**
   ```bash
   python main.py
   ```

---

## Testing Checklist

### Phase 1: API Persistence
- [ ] Mode persists across restart
- [ ] Database updated correctly
- [ ] Audit trail created
- [ ] API responses correct

### Phase 2: Execution Routing
- [ ] Mode switch affects next trade
- [ ] Client hot-swap works
- [ ] Error handling correct
- [ ] Insufficient funds handled gracefully

### Phase 3: Safety Gates
- [ ] Cannot switch with open positions
- [ ] Cannot switch with pending orders
- [ ] Credential validation works
- [ ] Confirmation required

### Phase 4: LIVE Enforcement
- [ ] Position size capped at 20%
- [ ] Leverage limited to 3x
- [ ] Daily loss auto-stop at 5%
- [ ] Drawdown stop at 15%
- [ ] Notifications working

### Phase 5: Real Trading
- [ ] Funds added to account
- [ ] Small trade executes
- [ ] Appears in VALR UI
- [ ] Tracked in database
- [ ] Limits enforced

---

## Expected Errors (NORMAL)

### During Testing (Zero Balance):
```
"Insufficient funds to place order"
"Account balance too low"
"Minimum order size not met"
```
**Status:** ✅ EXPECTED - Account has zero balance

### During Validation:
```
"Cannot switch to LIVE: open positions exist"
"Cannot switch to LIVE: pending orders exist"
"Cannot switch to LIVE: invalid VALR credentials"
```
**Status:** ✅ EXPECTED - Safety gates working

---

## User Action Points

### Before Starting:
1. ✅ Confirm backup complete
2. ✅ Understand insufficient funds are expected
3. ✅ Approve Phase 1 start

### After Phase 1:
1. 📝 Review changes
2. 🧪 Test mode persistence
3. ✅ Approve Phase 2

### After Phase 2:
1. 📝 Review changes
2. 🧪 Test mode switching
3. ✅ Approve Phase 3

### After Phase 3:
1. 📝 Review changes
2. 🧪 Test validation gates
3. ✅ Approve Phase 4

### After Phase 4:
1. 📝 Review ALL changes
2. 🧪 Test ALL safety features
3. 💰 **ADD FUNDS TO VALR ACCOUNT**
4. ✅ Approve LIVE testing

### After Phase 5:
1. 🎉 LIVE trading operational
2. 📊 Monitor first trades closely
3. 🔍 Verify all systems working

---

## Database Schema Reference

### trading_mode_state
```sql
id INTEGER PRIMARY KEY (always 1 - singleton)
current_mode VARCHAR(10) (PAPER or LIVE)
updated_at TIMESTAMP
updated_by VARCHAR(100)
```

### trading_mode_history
```sql
id SERIAL PRIMARY KEY
old_mode VARCHAR(10)
new_mode VARCHAR(10)
changed_at TIMESTAMP
changed_by VARCHAR(100)
reason TEXT
```

---

## API Endpoints

### Mode Management:
- `GET /api/trading/mode` - Get current mode
- `POST /api/trading/mode` - Set mode (body: `{"mode": "PAPER|LIVE"}`)
- `POST /api/trading/emergency-stop` - Emergency stop all trading

### Autonomous Engine:
- `GET /api/autonomous-engine/status` - Get engine status
- `POST /api/autonomous-engine/start` - Start autonomous trading
- `POST /api/autonomous-engine/stop` - Stop autonomous trading

---

## Success Metrics

### Phase 1:
- ✅ Mode persistence working
- ✅ No errors on restart
- ✅ Database audit working

### Phase 2:
- ✅ Dynamic client selection
- ✅ Mode switches effective
- ✅ Error handling correct

### Phase 3:
- ✅ All validations working
- ✅ Cannot bypass safety checks
- ✅ Clear error messages

### Phase 4:
- ✅ All limits enforced
- ✅ Auto-stops working
- ✅ Notifications sent

### Phase 5:
- ✅ Real trades execute
- ✅ Accurate tracking
- ✅ Safety maintained

---

## Emergency Contacts

### If Something Goes Wrong:
1. **Stop Trading Immediately:**
   - API: `POST /api/trading/emergency-stop`
   - Database: `UPDATE trading_mode_state SET current_mode = 'PAPER'`

2. **Restore Backup:**
   - Follow rollback procedure above

3. **Contact User:**
   - Report issue immediately
   - Provide error logs
   - Recommend next steps

---

*Skill Version: 1.0*
*Created: 2025-10-22*
*Purpose: Safe LIVE trading implementation*
