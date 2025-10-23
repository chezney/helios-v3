# GUI Development & Testing Focus

## Description
Focus area for building the Helios V3.0 trading GUI and validating system stability. Activates when you mention GUI, frontend, testing, or validation.

**Current Priority**: Build 3-component MVP, run 7-day stability test

---

## Current Status

### Backend: READY ✅
```
✅ 295 API endpoints operational
✅ WebSocket real-time updates working
✅ Authentication endpoints ready (JWT not implemented)
✅ CORS configured for localhost:3000
✅ All 5 tiers exposing data via APIs
```

### Frontend: NOT STARTED ❌
```
❌ No React components built
❌ No WebSocket client integration
❌ No UI framework selected (recommend Material-UI)
❌ No state management (recommend Zustand or Context)
❌ No charts library (recommend Recharts or TradingView)
```

### Testing: PARTIAL ⚠️
```
✅ 85+ unit tests passing (100% pass rate)
✅ Integration tests for each tier
⚠️ No end-to-end tests
❌ No 7-day continuous stability test
❌ No stress testing
❌ No performance benchmarks
```

---

## 3-Component MVP (Build This First)

### Component 1: Engine Controls
**File**: `helios-react/src/components/EngineControls.jsx`

**Purpose**: Start/Stop/Emergency Stop the autonomous engine

**API Endpoints**:
```javascript
POST /api/autonomous-engine/start
POST /api/autonomous-engine/stop
POST /api/autonomous-engine/emergency-stop
GET  /api/autonomous-engine/status
```

**UI Elements**:
- Status indicator (Running/Stopped/Error)
- Start button (green, disabled when running)
- Stop button (yellow, disabled when stopped)
- Emergency Stop button (red, always enabled)
- Current mode display (PAPER/LIVE)
- Uptime counter

**WebSocket Updates**:
- Subscribe to `engine_status` events
- Real-time status changes
- Error notifications

---

### Component 2: Portfolio Summary
**File**: `helios-react/src/components/PortfolioSummary.jsx`

**Purpose**: Show current portfolio value, P&L, and key metrics

**API Endpoints**:
```javascript
GET /api/portfolio/summary
GET /api/portfolio/state/current
GET /api/portfolio/performance/metrics
```

**UI Elements**:
- Total portfolio value (ZAR)
- Total P&L (amount + percentage, color-coded)
- Available balance
- Allocated balance
- Number of open positions
- Win rate (%)
- Sharpe ratio
- Max drawdown

**WebSocket Updates**:
- Subscribe to `portfolio_update` events
- Real-time P&L updates
- Balance changes

---

### Component 3: Positions List
**File**: `helios-react/src/components/PositionsList.jsx`

**Purpose**: Show all open positions with current status

**API Endpoints**:
```javascript
GET  /api/portfolio/positions
GET  /api/portfolio/positions/{position_id}
POST /api/portfolio/positions/{position_id}/close
```

**UI Elements**:
- Table/List of open positions
- Columns:
  - Pair (BTCZAR, ETHZAR, SOLZAR)
  - Side (LONG/SHORT)
  - Entry price
  - Current price
  - Quantity
  - Unrealized P&L (color-coded)
  - Age (time since opened)
  - Close button
- Filter by pair/side
- Sort by P&L/Age

**WebSocket Updates**:
- Subscribe to `position_update` events
- Real-time price updates
- P&L recalculation
- Position open/close events

---

## Technology Stack (Recommended)

### Frontend Framework
```
React 18+ with Vite
- Fast dev server
- Hot module replacement
- Modern build tooling
```

### UI Library
```
Material-UI (MUI) v5
- Professional components
- Responsive design
- Dark mode support
- Customizable theme
```

### State Management
```
Zustand (lightweight) OR React Context
- Simple API
- No boilerplate
- TypeScript support
```

### WebSocket Client
```
WebSocket API (native) OR socket.io-client
- Real-time updates
- Auto-reconnect
- Event subscriptions
```

### Charts
```
Recharts (simple) OR TradingView Lightweight Charts
- Candlestick charts
- Real-time updates
- Performance metrics
```

### HTTP Client
```
Axios OR fetch API
- API calls to FastAPI backend
- Request/response interceptors
- Error handling
```

---

## WebSocket Integration Pattern

### Connection Setup
```javascript
// src/services/websocket.js
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
  console.log('WebSocket connected');
  // Subscribe to events
  ws.send(JSON.stringify({
    type: 'subscribe',
    events: ['engine_status', 'portfolio_update', 'position_update']
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Update component state based on event type
  handleWebSocketEvent(data);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket closed, reconnecting...');
  setTimeout(connectWebSocket, 5000); // Reconnect after 5s
};
```

### Event Types
```javascript
// Engine status events
{
  type: 'engine_status',
  data: {
    running: true,
    mode: 'PAPER',
    uptime_seconds: 3600,
    last_decision: '2025-10-21T10:30:00Z'
  }
}

// Portfolio update events
{
  type: 'portfolio_update',
  data: {
    total_value: 100000.00,
    total_pnl: 2500.00,
    pnl_percent: 2.56,
    open_positions: 3
  }
}

// Position update events
{
  type: 'position_update',
  data: {
    position_id: 123,
    pair: 'BTCZAR',
    unrealized_pnl: 1250.00,
    current_price: 1234567.89
  }
}
```

---

## API Endpoints Quick Reference

### Engine Control
```
GET    /api/autonomous-engine/status
POST   /api/autonomous-engine/start
POST   /api/autonomous-engine/stop
POST   /api/autonomous-engine/emergency-stop
GET    /api/autonomous-engine/decision-log
GET    /api/autonomous-engine/performance-metrics
```

### Portfolio
```
GET    /api/portfolio/summary
GET    /api/portfolio/state/current
GET    /api/portfolio/positions
GET    /api/portfolio/positions/{position_id}
POST   /api/portfolio/positions/{position_id}/close
GET    /api/portfolio/performance/metrics
GET    /api/portfolio/risk-metrics
```

### Market Data
```
GET    /api/market/candles/{pair}?timeframe=1m&limit=100
GET    /api/market/features/latest/{pair}
GET    /api/market/summary/{pair}
GET    /api/market/price/{pair}
```

### Trading Decisions
```
GET    /api/tier2/predictions/latest/{pair}
GET    /api/tier3/risk-decision/latest/{pair}
GET    /api/tier4/llm-decision/latest/{pair}
```

---

## MVP Build Steps (Week 4 of Simplification Plan)

### Day 1: Project Setup
```bash
# Create React app
npm create vite@latest helios-react -- --template react
cd helios-react
npm install

# Install dependencies
npm install @mui/material @emotion/react @emotion/styled
npm install axios
npm install recharts  # if using charts

# Install dev dependencies
npm install -D @vitejs/plugin-react
```

### Day 2: Component Structure
```
helios-react/
├── src/
│   ├── components/
│   │   ├── EngineControls.jsx
│   │   ├── PortfolioSummary.jsx
│   │   └── PositionsList.jsx
│   ├── services/
│   │   ├── api.js          # Axios instance
│   │   └── websocket.js    # WebSocket client
│   ├── hooks/
│   │   ├── useWebSocket.js
│   │   └── usePortfolio.js
│   ├── App.jsx
│   └── main.jsx
```

### Day 3: Implement Components
1. Create EngineControls component
2. Create PortfolioSummary component
3. Create PositionsList component
4. Wire up API calls
5. Add error handling

### Day 4: WebSocket Integration
1. Create WebSocket service
2. Add reconnection logic
3. Subscribe to events
4. Update components on events
5. Test real-time updates

### Day 5: Polish & Testing
1. Add Material-UI theming
2. Add loading states
3. Add error states
4. Test all functionality
5. Fix bugs

---

## Testing Strategy

### 7-Day Continuous Stability Test

**Purpose**: Prove system can run autonomously for 7 days without crashes

**Setup** (4 hours):
```bash
# 1. Setup monitoring
python scripts/setup_paper_trading.py

# 2. Clear previous data
python scripts/clear_all_data.py --confirm

# 3. Start system
python main.py

# 4. Start autonomous engine via API
curl -X POST http://localhost:8000/api/autonomous-engine/start

# 5. Monitor every 6 hours
python scripts/monitor_paper_trading.py
```

**What to Monitor**:
- System uptime
- Memory usage (should stay stable, not leak)
- Database connections (should not grow unbounded)
- WebSocket connections (should auto-reconnect)
- API response times (should stay <200ms)
- Trade execution (should complete without errors)
- Error logs (should be minimal)

**Success Criteria**:
- ✅ No crashes for 7 days
- ✅ Memory usage stable (<2GB)
- ✅ All 3 async loops operational
- ✅ WebSocket connected 99%+ of time
- ✅ At least 10 paper trades executed
- ✅ No critical errors in logs

**Failure Scenarios**:
- ❌ System crashes (restart test)
- ❌ Memory leak (fix, restart test)
- ❌ Database timeout (fix, restart test)
- ❌ WebSocket disconnect >1 hour (fix, restart test)

---

### Stress Testing (After 7-Day Test)

**Load Test**:
```bash
# Install artillery
npm install -g artillery

# Create load test config
# artillery/load-test.yml
config:
  target: 'http://localhost:8000'
  phases:
    - duration: 300
      arrivalRate: 50  # 50 req/sec

scenarios:
  - flow:
    - get:
        url: '/api/portfolio/summary'
    - get:
        url: '/api/market/candles/BTCZAR?timeframe=1m'
    - get:
        url: '/api/autonomous-engine/status'

# Run test
artillery run artillery/load-test.yml
```

**Performance Benchmarks**:
```python
# scripts/benchmark_api.py
import asyncio
import aiohttp
import time

async def benchmark():
    endpoints = [
        '/api/portfolio/summary',
        '/api/market/candles/BTCZAR?timeframe=1m',
        '/api/autonomous-engine/status'
    ]

    # 1000 requests per endpoint
    # Measure p50, p95, p99 latency
    # Target: p99 < 500ms
```

---

## Known Issues & Limitations

### Backend (Already Implemented)
```
✅ All endpoints functional
⚠️ No authentication (JWT planned but not implemented)
⚠️ CORS allows all origins (hardcode localhost:3000 for now)
❌ No rate limiting
❌ No HTTPS (using HTTP)
```

### Frontend (Not Started)
```
❌ No error boundary
❌ No loading states
❌ No offline detection
❌ No responsive design
❌ No accessibility (a11y)
```

### Testing Gaps
```
✅ Unit tests for all tiers
⚠️ Integration tests (some missing)
❌ E2E tests (none)
❌ Load tests (none)
❌ 7-day stability test (not run)
```

---

## Quick Wins (Do These First)

### GUI Quick Win
```
Instead of planning 8 components, BUILD 3 NOW:
1. EngineControls - 2-4 hours
2. PortfolioSummary - 2-4 hours
3. PositionsList - 3-6 hours

Total: 7-14 hours = 1-2 days

Result: Working MVP GUI
```

### Testing Quick Win
```
Instead of planning comprehensive tests, RUN 7-DAY TEST NOW:
1. Setup monitoring - 1 hour
2. Start autonomous engine - 5 minutes
3. Let it run - 7 days
4. Check results - 2 hours

Total: 3 hours + 7 days wait

Result: Proven stability or identified bugs
```

---

## Anti-Patterns to Avoid

### Over-Planning (We Did This)
```
❌ Spec 8 complex components before building 1
❌ Plan comprehensive test suite before running 1 test
❌ Design perfect architecture before MVP

✅ Build 3 components, test, iterate
✅ Run 7-day test, fix issues, re-run
✅ Ship MVP, get feedback, improve
```

### Analysis Paralysis (We Did This)
```
❌ "Which chart library should we use?" (spend 4 hours researching)
❌ "Should we use Redux or Zustand?" (debate for 2 days)
❌ "What's the perfect color scheme?" (design for a week)

✅ Pick Recharts, move on (can change later)
✅ Use React Context, move on (can refactor later)
✅ Use Material-UI defaults, move on (can customize later)
```

### Premature Optimization (Don't Do This)
```
❌ Optimize API response times before measuring
❌ Add caching before knowing it's needed
❌ Implement complex state management before simple fails

✅ Build first, measure, THEN optimize
✅ Add caching when you have slow endpoints
✅ Use Context first, upgrade to Zustand if needed
```

---

## Success Metrics

### MVP GUI Success
```
✅ Can start/stop engine from UI
✅ Can see portfolio value and P&L
✅ Can view open positions
✅ Real-time updates via WebSocket
✅ No crashes during 1-hour usage
```

### 7-Day Test Success
```
✅ System runs for 7 days straight
✅ No memory leaks
✅ No crashes
✅ At least 10 paper trades
✅ Error rate <1%
```

### Production Readiness
```
MVP GUI ✅
7-Day Test ✅
VALR Client ✅ (implement in Week 3)
Security ⚠️ (JWT, HTTPS - do later)
Performance ✅ (p99 <500ms)
```

---

## Next Steps (Concrete Actions)

### This Week
1. Create `helios-react/` project with Vite
2. Install Material-UI, Axios
3. Build EngineControls component
4. Build PortfolioSummary component
5. Build PositionsList component
6. Integrate WebSocket for real-time updates
7. Test with running backend

### Next Week
1. Start 7-day continuous stability test
2. Monitor system daily
3. Fix any issues that arise
4. Document test results

### Week After
1. Review 7-day test results
2. Add more GUI components if MVP successful
3. Implement VALR live client
4. Security hardening

---

## Remember

**GUI Development**:
- Build 3 components first (MVP)
- Don't plan 8 components
- Ship, test, iterate

**Testing**:
- Run 7-day test ASAP
- Fix issues as they arise
- Re-run if it fails

**General Approach**:
- Build > Plan
- Ship > Perfect
- Iterate > Analyze

**You're 95% complete on the backend. Focus on:**
1. MVP GUI (7-14 hours)
2. 7-Day Test (3 hours + 7 days)
3. VALR Client (8-16 hours)

Then you're production-ready (minus security).
