# Helios V3.0 Trading System - Essential Context

## Description
Essential context about the Helios autonomous trading system. Activates when you ask about system capabilities, request code changes, or need to understand what's implemented.

**Purpose**: Compressed knowledge from 11,400-line PRD + 90+ docs → Single reference

---

## System Status (Quick Facts)

**Current State**: 95% Complete - All 5 tiers operational
**Mode**: PAPER trading (fully functional)
**Missing**: VALR live client (5%), security hardening

### What Works ✅
- 5-tier intelligence pipeline (data → ML → risk → LLM → portfolio)
- Autonomous trading engine (3 async loops)
- Real-time WebSocket data (auto-starts with server)
- Paper trading with realistic execution
- All 295 API endpoints functional
- 85+ tests passing (100% pass rate)

### What's Missing ❌
- VALR live trading client (`src/trading/execution/valr_trading_client.py`)
- 7-day continuous stability test
- Security (JWT auth, HTTPS)
- GUI (backend ready, frontend not started)

---

## 5-Tier Architecture

```
Tier 1: Data Foundation ✅
  → VALR WebSocket (auto-starts)
  → Multi-timeframe candles (1m, 5m, 15m, 1h, 4h, 1d)
  → 90-dimensional features (30 per timeframe)
  → Files: src/data/

Tier 2: Neural Network ✅
  → AutoGluon ensemble model
  → <50ms inference
  → BUY/SELL/HOLD predictions + confidence
  → Files: src/ml/

Tier 3: Risk Management ✅
  → GARCH(1,1) volatility
  → Kelly Criterion position sizing (0.25x fractional)
  → Dynamic leverage (1.0x - 3.0x)
  → Files: src/risk/

Tier 4: LLM Strategic Layer ✅
  → Multi-model (Claude + GPT-4)
  → Market context analysis
  → APPROVE/MODIFY/REJECT decisions
  → Files: src/llm/

Tier 5: Portfolio Manager ✅
  → 7 institutional risk checks
  → MPT + Black-Litterman optimization
  → Position lifecycle management
  → Files: src/portfolio/

Autonomous Engine ✅
  → Orchestrates all 5 tiers
  → 3 concurrent loops (decisions, monitoring, metrics)
  → Paper/Live mode switching
  → Files: src/trading/autonomous/
```

---

## Key File Locations

```
main.py                              # FastAPI entry (auto-starts WebSocket)
config/settings.py                   # Global config
config/risk_config.py                # Risk parameters (GARCH, Kelly, leverage)

src/data/collectors/valr_websocket_client.py       # WebSocket
src/data/processors/feature_engineering.py         # 90 features
src/ml/inference/predictor.py                      # ML predictions
src/risk/aether_engine.py                          # Risk orchestrator
src/llm/orchestrator/llm_orchestrator.py          # LLM decisions
src/portfolio/portfolio_risk_manager.py            # Portfolio checks
src/trading/autonomous/trading_engine.py           # Autonomous engine
```

---

## Database (21 Tables)

**Tier 1**: market_summary, trades, market_ohlc, ml_features
**Tier 2**: ml_models, ml_predictions, model_performance
**Tier 3**: volatility_forecasts, aether_risk_decisions
**Tier 4**: llm_strategic_decisions, market_context_snapshots
**Tier 5**: positions, portfolio_state, portfolio_snapshots

---

## Critical API Endpoints

**Engine Control**:
- POST `/api/autonomous-engine/start` - Start engine
- POST `/api/autonomous-engine/stop` - Stop engine
- POST `/api/autonomous-engine/emergency-stop` - Emergency halt
- GET `/api/autonomous-engine/status` - Engine status

**Trading Mode**:
- GET `/api/orchestrator/system/trading/mode` - Get mode
- PUT `/api/orchestrator/system/trading/mode` - Set PAPER/LIVE

**Data**:
- GET `/api/market/candles/{pair}?timeframe=1m` - Get candles
- GET `/api/market/features/latest/{pair}` - Get features

---

## Configuration Quick Reference

### Risk Parameters (`config/risk_config.py`)
```python
KELLY_CONFIG = {
    'fractional_kelly': 0.25,      # Conservative 25% Kelly
    'max_position_pct': 0.20       # Max 20% of portfolio
}

LEVERAGE_CONFIG = {
    'base_leverage': 1.0,          # Start at spot
    'max_leverage': 3.0            # Never exceed 3x
}

REGIME_THRESHOLDS = {
    'BTCZAR': {'low': 0.02, 'medium': 0.04, 'high': 0.06}
}
```

---

## Common Tasks

### Start System
```bash
# DON'T run without asking user first
python main.py
```

### Check Status
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/autonomous-engine/status
```

### Verify Data
```bash
python check_latest_candles.py
python check_features_quick.py
python verify_tier1_data.py
```

---

## Documentation Structure

**Main Docs** (Read These First):
- `docs/PROJECT_STATUS_REPORT.md` - Overall status
- `docs/COMPLETE_SYSTEM_DOCUMENTATION.md` - Architecture
- `docs/guides/WHAT_IS_MISSING.md` - Gap analysis
- `FINAL_ASSESSMENT_AND_RECOMMENDATIONS.md` - Complexity assessment (root)

**Phase Docs**:
- `docs/phase1/PHASE_1_COMPLETE.md` - Tier 1 complete
- `docs/phase2/PHASE2_COMPLETE.md` - Tier 2 complete
- `docs/phase3/PHASE3_COMPLETE.md` - Tier 3 complete
- `docs/phase4/PHASE4_COMPLETE.md` - Tier 4 complete
- `docs/phase5/PHASE5_COMPLETE.md` - Tier 5 complete

**PRD**: `docs/HELIOS_V3_COMPLETE_PRD.md` (11,400 lines - read in sections)

---

## Testing

```bash
# All tests
pytest tests/ -v

# Specific tier
pytest tests/tier1/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

**Status**: 85+ tests, 100% pass rate

---

## Known Issues

**Over-Engineered** (Simplify):
- 90 features → Reduce to 60 (some redundant)
- 295 API endpoints → Consolidate to 80
- 90+ docs → Consolidate to 30

**Missing/Broken** (Fix):
- VALR live client (not implemented)
- Some microstructure features (placeholders)
- 7-day continuous test (not run)
- Security (no auth, no HTTPS)

---

## Critical Rules (from docs/CLAUDE.md)

**NEVER**:
- ❌ Write placeholder code (TODOs, stubs, NotImplementedError)
- ❌ Use mock/fake data in dev/prod
- ❌ Start main.py without asking user
- ❌ Overwrite .env without permission

**ALWAYS**:
- ✅ Search for existing code before creating new
- ✅ Read PRD section before implementing
- ✅ Use real data (database queries, API calls)
- ✅ Write tests for new functionality
- ✅ Document code changes

---

## When to Use This Skill

This Skill auto-activates when you:
- Ask "How does X work?"
- Request "Add feature Y"
- Mention "PRD", "docs", "status"
- Need context about the system
- Before making code changes

**Token Efficiency**: This Skill (~500 lines) replaces reading 11,400-line PRD = **95% token savings**

---

## Quick Answers

**Q: Can I trade now?**
A: YES in PAPER mode. NO in LIVE mode (need VALR client).

**Q: What's the system completion?**
A: 95% complete. All 5 tiers operational. Missing: VALR live client, security.

**Q: Where's the GUI?**
A: Backend ready (295 endpoints, WebSocket). Frontend not started (see GUI_FOCUS.md).

**Q: Is it stable?**
A: Paper trading works. Need 7-day continuous test to prove production stability.

**Q: What should I work on next?**
A: Options:
1. GUI (3-component MVP)
2. VALR live client (enable real trading)
3. Simplify (reduce features/endpoints/docs)
4. 7-day stability test

---

## Summary

**System**: 95% complete, all tiers operational
**Strength**: Excellent architecture, working autonomous engine
**Weakness**: Over-engineered (too many features/endpoints/docs)
**Next**: Simplify + GUI + VALR client = Production ready

**Remember**: System is 95% done. Don't add more complexity. Simplify, then ship.
