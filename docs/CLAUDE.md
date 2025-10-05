# Helios Trading System V3.0 - AI Coding Guidelines

> **MANDATORY REQUIREMENTS FOR ALL AI CODERS**
> Version: 3.1.0 | Date: January 2025 | Project: Helios Trading System V3.0
> Platform: Windows 11 + WSL2 Ubuntu 22.04 + RTX 4060 (8GB/12GB)
> **NEW:** Modular Architecture - Build the Plane While Flying

---

## 🚨 CRITICAL ANTI-PLACEHOLDER RULES

### **RULE ZERO: ABSOLUTELY NO PLACEHOLDERS - EVER**

**NEVER, UNDER ANY CIRCUMSTANCES:**
- ❌ Write `# TODO: implement this later`
- ❌ Write `pass  # placeholder`
- ❌ Write `raise NotImplementedError("Coming soon")`
- ❌ Write stub functions that return dummy data
- ❌ Write comments like `# This will be implemented in Phase 2`
- ❌ Leave empty function bodies
- ❌ Return hardcoded test values in production code
- ❌ Create skeleton classes without full implementation
- ❌ Write "mock" or "stub" methods in dev/prod environments

### **WHAT TO DO INSTEAD:**

✅ **If you don't know how to implement something:**
   - STOP and ASK the user for clarification
   - Research the existing codebase for similar implementations
   - Consult the HELIOS_V3_COMPLETE_PRD.md for specifications

✅ **If a feature is complex:**
   - Break it into smaller, fully-implementable parts
   - Implement each part COMPLETELY before moving to the next
   - If you can't complete it in one go, implement the first complete piece and ask before continuing

✅ **If you need data:**
   - Use REAL data from the database
   - Use REAL API calls to VALR/Claude/OpenAI
   - Use REAL calculations, not fake return values
   - Query actual InfluxDB/PostgreSQL data

✅ **If something is missing:**
   - Implement it FULLY based on the PRD specifications
   - Don't leave stubs - write the complete working code
   - Test it before considering it done

### **EXAMPLES OF VIOLATIONS (NEVER DO THIS):**

```python
# ❌ WRONG - NEVER DO THIS
def calculate_sharpe_ratio(returns: List[float]) -> float:
    """Calculate Sharpe ratio."""
    # TODO: implement actual Sharpe calculation
    return 1.5  # placeholder value

# ❌ WRONG - NEVER DO THIS
class PortfolioManager:
    def optimize_allocation(self):
        """Optimize portfolio allocation."""
        pass  # will implement later

# ❌ WRONG - NEVER DO THIS
def get_market_data(symbol: str):
    # Mock data for testing
    return {
        "price": 850000,
        "volume": 100
    }  # Replace with real API call
```

### **EXAMPLES OF CORRECT IMPLEMENTATION:**

```python
# ✅ CORRECT - FULL IMPLEMENTATION
def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    """
    Calculate Sharpe ratio.

    Formula: (Mean Return - Risk-Free Rate) / Standard Deviation of Returns
    """
    if not returns or len(returns) < 2:
        raise ValueError("Need at least 2 return values to calculate Sharpe ratio")

    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)

    if std_return == 0:
        return 0.0

    sharpe = (mean_return - risk_free_rate) / std_return
    return float(sharpe)

# ✅ CORRECT - FULL IMPLEMENTATION
class PortfolioManager:
    def __init__(self, db_session):
        self.db = db_session

    def optimize_allocation(self, symbols: List[str], target_return: float) -> Dict[str, float]:
        """
        Optimize portfolio allocation using Modern Portfolio Theory.

        Returns allocation weights for each symbol.
        """
        # Fetch historical returns for all symbols
        returns_matrix = self._fetch_historical_returns(symbols)

        # Calculate covariance matrix
        cov_matrix = np.cov(returns_matrix.T)

        # Mean returns vector
        mean_returns = np.mean(returns_matrix, axis=0)

        # Optimization using scipy
        from scipy.optimize import minimize

        n_assets = len(symbols)
        init_weights = np.array([1/n_assets] * n_assets)

        # Constraints: weights sum to 1
        constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
        bounds = tuple((0, 1) for _ in range(n_assets))

        # Minimize portfolio variance for target return
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))

        result = minimize(
            portfolio_variance,
            init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )

        # Return optimized weights
        return dict(zip(symbols, result.x))

# ✅ CORRECT - FULL IMPLEMENTATION WITH REAL API
async def get_market_data(symbol: str) -> Dict[str, Any]:
    """Fetch real-time market data from VALR API."""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.valr.com/v1/public/{symbol}/marketsummary"
        async with session.get(url) as response:
            if response.status != 200:
                raise APIError(f"VALR API returned {response.status}")

            data = await response.json()
            return {
                "symbol": symbol,
                "last_price": float(data["lastTradedPrice"]),
                "bid_price": float(data["bidPrice"]),
                "ask_price": float(data["askPrice"]),
                "volume": float(data["baseVolume"]),
                "timestamp": datetime.utcnow()
            }
```

---

## 🚨 SERVER MANAGEMENT RULES

### **NEVER START MAIN.PY WITHOUT ASKING**
**ALWAYS ask the user before starting the server with `uvicorn main:app` or `python main.py`**

### **USE ORCHESTRATOR FOR:**
- ALL trading operations (orders, positions, balances)
- Portfolio data (needs mode awareness for paper vs live)
- Mode switching (paper/live)
- AI predictions and strategy execution
- Risk management during active trading
- Emergency controls
- Any operation that needs paper/live mode awareness

### **USE DIRECT API FOR:**
- Read-only market data (prices, orderbooks, tickers) - NO AUTH REQUIRED
- Historical data queries (past trades, candles)
- Static configurations
- Health checks
- Historical balance/transaction records

---

## 🚨 CORE MANDATORY RULES - NON-NEGOTIABLE

**These 22 rules (20 original + Rule Zero + Modularity) are the foundation of ALL coding work on Helios V3.0 and MUST be followed without exception:**

### 0. NO PLACEHOLDERS EVER ⚠️
**NEVER write placeholder code, TODOs, stubs, or mock data in dev/prod. Every function must be FULLY IMPLEMENTED with real logic, real data, and real calculations. If you can't implement something completely, STOP and ASK.**

### 0.5. USE MODULAR ARCHITECTURE ⚠️ NEW
**ALWAYS use the modular architecture for safe deployments. Use feature flags for gradual rollouts, test modules before deployment, and use circuit breakers for critical components. See MODULAR_ARCHITECTURE_GUIDE.md for details.**

### 1. Server Management After Changes
**After making changes, ALWAYS make sure to start up a new server so I can test it.**

### 2. Code Iteration Over Creation
**Always look for existing code to iterate on instead of creating new code.**

### 3. Pattern Preservation
**Do not drastically change the patterns before trying to iterate on existing patterns.**

### 4. Server Cleanup Before Testing
**Always kill all existing related servers that may have been created in previous testing before trying to start a new server.**

### 5. Simple Solutions First
**Always prefer simple solutions.**

### 6. Avoid Code Duplication
**Avoid duplication of code whenever possible, which means checking for other areas of the codebase that might already have similar code and functionality.**

### 7. Environment-Aware Code
**Write code that takes into account the different environments: dev, test, and prod.**

### 8. Focused Changes Only
**You are careful to only make changes that are requested or you are confident are well understood and related to the change being requested.**

### 9. Exhaust Existing Solutions First
**When fixing an issue or bug, do not introduce a new pattern or technology without first exhausting all options for the existing implementation. And if you finally do this, make sure to remove the old implementation afterwards so we don't have duplicate logic.**

### 10. Clean and Organized Codebase
**Keep the codebase very clean and organized.**

### 11. Avoid One-Time Scripts in Files
**Avoid writing scripts in files if possible, especially if the script is likely only to be run once.**

### 12. File Size Management
**Avoid having files over 200-300 lines of code. Refactor at that point.**

### 13. No Mock Data in Dev/Prod
**Mocking data is only needed for tests, never mock data for dev or prod.**

### 14. No Fake Data Patterns
**Never add stubbing or fake data patterns to code that affects the dev or prod environments.**

### 15. Environment File Protection
**Never overwrite my .env file without first asking and confirming.**

### 16. Task-Relevant Focus
**Focus on the areas of code relevant to the task.**

### 17. Avoid Unrelated Changes
**Do not touch code that is unrelated to the task.**

### 18. Comprehensive Testing
**Write thorough tests for all major functionality.**

### 19. Preserve Working Patterns
**Avoid making major changes to the patterns and architecture of how a feature works, after it has shown to work well, unless explicitly instructed.**

### 20. Impact Analysis
**Always think about what other methods and areas of code might be affected by code changes.**

---

## 🖥️ PLATFORM-SPECIFIC REQUIREMENTS (Windows 11 WSL2)

### **Development Environment:**
- **Host OS:** Windows 11 (64-bit) Build 22000+
- **WSL2:** Ubuntu 22.04 LTS (all development happens here)
- **GPU:** NVIDIA RTX 4060 (8GB or 12GB VRAM) - PRIMARY TARGET
- **Docker:** Docker Desktop with WSL2 backend
- **File Location:** Store project in WSL2 filesystem (`~/helios-v3`), NOT Windows filesystem (`/mnt/c/`)

### **Critical WSL2 Considerations:**

1. **File Paths:**
   ```python
   # ✅ CORRECT - WSL2 filesystem (fast)
   MODEL_PATH = "/home/username/helios-v3/models/neural_network.pt"

   # ❌ WRONG - Windows filesystem (3-5× slower)
   MODEL_PATH = "/mnt/c/Users/username/helios-v3/models/neural_network.pt"
   ```

2. **GPU Access:**
   ```python
   # ✅ CORRECT - Check CUDA availability in WSL2
   import torch
   if torch.cuda.is_available():
       device = torch.device("cuda:0")
       print(f"Using GPU: {torch.cuda.get_device_name(0)}")  # Should show RTX 4060
   else:
       raise RuntimeError("GPU not available in WSL2")
   ```

3. **Docker Commands:**
   ```bash
   # ✅ CORRECT - Use Docker with GPU support in WSL2
   docker run --gpus all --runtime=nvidia helios:latest

   # Check GPU is accessible
   docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   ```

4. **Environment Variables:**
   ```bash
   # WSL2-specific optimizations
   export CUDA_VISIBLE_DEVICES=0
   export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
   ```

---

## 🎯 RTX 4060 GPU OPTIMIZATION (MANDATORY)

### **Memory Constraints:**
- **8GB VRAM:** Must use ALL optimizations below
- **12GB VRAM:** Can relax batch size, still use FP16

### **REQUIRED Optimizations (Already in PRD):**

```python
# This configuration is MANDATORY for RTX 4060 8GB
TRAINING_CONFIG_4060 = {
    'batch_size': 16,              # ✅ Reduced for 8GB VRAM
    'accumulation_steps': 2,       # ✅ Effective batch size = 32
    'mixed_precision': True,       # ✅ CRITICAL - Use FP16
    'gradient_checkpointing': True,# ✅ CRITICAL - Saves 40% VRAM
    'pin_memory': True,            # ✅ Faster CPU→GPU transfer
    'num_workers': 4,              # ✅ Optimal for 6-core CPU
    'prefetch_factor': 2,          # ✅ Pre-load 2 batches
}

# NEVER use batch_size > 16 on RTX 4060 8GB
# NEVER disable mixed_precision on RTX 4060
# NEVER disable gradient_checkpointing on RTX 4060
```

### **Model Loading:**

```python
# ✅ CORRECT - Load model with GPU optimization
def load_model_optimized():
    model = Helios4060OptimizedModel()

    # Move to GPU with mixed precision
    model = model.to('cuda')
    model = model.half()  # Convert to FP16

    # Enable gradient checkpointing
    for lstm in [model.hfp_lstm, model.mfp_lstm, model.lfp_lstm]:
        lstm.register_backward_hook(checkpoint_hook)

    return model

# ❌ WRONG - Don't do this on RTX 4060 8GB
def load_model_wrong():
    model = LargeModel()
    model = model.to('cuda')  # No FP16, no checkpointing - WILL OOM!
    return model
```

---

## 📊 COMPLETE API ENDPOINT REFERENCE

**Total Endpoints: 295**
- **57 Orchestrator Endpoints**: Data collection, monitoring, auto-trading
- **238 Direct API Endpoints**: Trading, market data, portfolio, analytics

### **CRITICAL: Trading Mode Safety**
```python
# ✅ ALWAYS verify mode before trading operations
async def execute_trade(symbol: str, side: str, quantity: float):
    # Check current trading mode
    response = await http_client.get("http://localhost:8000/api/orchestrator/system/trading/mode")
    mode = response.json()["mode"]

    if mode == "LIVE":
        # Require explicit confirmation for LIVE trades
        logger.warning(f"⚠️ LIVE MODE - Real money trade: {symbol} {side} {quantity}")
        # Execute on real VALR API
        await valr_client.place_order(symbol, side, quantity)
    else:
        # Paper mode - simulated execution
        logger.info(f"📝 PAPER MODE - Simulated trade: {symbol} {side} {quantity}")
        await paper_trading_service.simulate_order(symbol, side, quantity)
```

### **Key Endpoint Categories:**

#### **Orchestrator Endpoints (Mode-Aware):**
- `/api/orchestrator/system/trading/mode` (GET/PUT) - Get/set trading mode
- `/api/orchestrator/auto-trading/enable` (POST) - Enable autonomous trading
- `/api/orchestrator/auto-trading/disable` (POST) - Disable autonomous trading
- `/api/orchestrator/auto-trading/status` (GET) - Auto-trading status
- `/api/orchestrator/trading/orders` (GET) - Get orders (mode-aware)
- `/api/orchestrator/balances/current` (GET) - Current balances (mode-aware)

#### **Direct Trading Endpoints:**
- `/api/trading/orders/market` (POST) - Place market order
- `/api/trading/orders/limit` (POST) - Place limit order
- `/api/trading/positions` (GET) - Get open positions
- `/api/trading/order-history` (GET) - Historical orders

#### **Market Data (No Auth Required):**
- `/api/market/ticker/{pair}` (GET) - Current price ticker
- `/api/market/orderbook/{pair}` (GET) - Order book depth
- `/api/prices/ohlc/{pair}` (GET) - OHLC candlestick data

#### **Portfolio Management:**
- `/api/portfolio/summary` (GET) - Portfolio overview with metrics
- `/api/portfolio/performance` (GET) - Performance analytics
- `/api/portfolio/risk-analysis` (GET) - Risk metrics (VaR, Sharpe, etc.)

#### **Neural Network / AI:**
- `/api/analytics/predictions/latest` (GET) - Latest predictions
- `/api/analytics/neural-network/status` (GET) - Model status
- `/api/llm/decisions/recent` (GET) - Recent LLM strategic decisions

#### **Risk Management:**
- `/api/risk/metrics` (GET) - Current risk metrics
- `/api/risk/limits` (GET/PUT) - Risk limit configuration
- `/api/risk-control/emergency-stop` (POST) - Emergency stop all trading

**See CLAUDE.md lines 93-303 for complete endpoint list.**

---

## 🔄 DEVELOPMENT WORKFLOW

### **Code Change Process (MANDATORY SEQUENCE):**

1. **Kill existing servers**
   ```bash
   # In WSL2 terminal
   docker-compose down
   pkill -f "uvicorn"
   pkill -f "python main.py"
   ```

2. **Search for existing code**
   ```bash
   # Use grep to find similar implementations
   grep -r "class PortfolioManager" src/
   grep -r "def calculate_sharpe" src/
   ```

3. **Read the PRD specification**
   ```bash
   # Find the relevant section in PRD
   grep -n "Portfolio Manager" HELIOS_V3_COMPLETE_PRD.md
   ```

4. **Implement COMPLETE solution (NO PLACEHOLDERS)**
   - Write full working code
   - Use real data sources
   - Include all error handling
   - Add comprehensive docstrings
   - Write unit tests

5. **Test the implementation**
   ```bash
   # Run tests
   pytest tests/test_portfolio.py -v

   # Start server
   docker-compose up -d

   # Test endpoint
   curl http://localhost:8000/api/portfolio/summary
   ```

6. **Verify GPU usage (if ML code)**
   ```bash
   # Check GPU utilization
   nvidia-smi dmon -s u -c 10

   # Should show GPU activity during training/inference
   ```

7. **Update documentation**
   - Add docstrings to all functions
   - Update API documentation if endpoints changed
   - Add comments for complex logic

---

## 🚨 CRITICAL DON'TS

### **CODE QUALITY:**
- ❌ **DON'T** write placeholder code or TODOs
- ❌ **DON'T** return hardcoded test values in production code
- ❌ **DON'T** create stub functions with `pass` or `raise NotImplementedError`
- ❌ **DON'T** duplicate code - search for existing implementations first
- ❌ **DON'T** create files over 200-300 lines - refactor into modules
- ❌ **DON'T** ignore existing patterns - iterate on them

### **DATA & TESTING:**
- ❌ **DON'T** use mock/fake data in dev or prod environments
- ❌ **DON'T** skip writing tests for new functionality
- ❌ **DON'T** hardcode API keys or secrets in code
- ❌ **DON'T** commit sensitive data to git

### **SERVER MANAGEMENT:**
- ❌ **DON'T** start servers without killing existing ones first
- ❌ **DON'T** start main.py without asking the user
- ❌ **DON'T** modify .env file without permission

### **SCOPE & CHANGES:**
- ❌ **DON'T** make unrelated changes to the codebase
- ❌ **DON'T** change working patterns without explicit instruction
- ❌ **DON'T** ignore impact on other code areas

### **WSL2 & GPU:**
- ❌ **DON'T** store project files in `/mnt/c/` (Windows filesystem)
- ❌ **DON'T** disable mixed precision on RTX 4060
- ❌ **DON'T** use batch sizes > 16 on RTX 4060 8GB
- ❌ **DON'T** disable gradient checkpointing on RTX 4060

---

## ✅ IMPLEMENTATION CHECKLIST

Before completing ANY task, verify:

### **Rule Zero - No Placeholders:**
- [ ] No `TODO` comments in code
- [ ] No `pass` in function bodies
- [ ] No `NotImplementedError` exceptions
- [ ] No hardcoded test return values
- [ ] All functions fully implemented with real logic

### **Core 20 Rules:**
- [ ] **Rule 1:** New server started for testing
- [ ] **Rule 2:** Existing code iterated upon
- [ ] **Rule 3:** Existing patterns preserved
- [ ] **Rule 4:** Old servers killed before new start
- [ ] **Rule 5:** Simple solution implemented
- [ ] **Rule 6:** Code duplication avoided
- [ ] **Rule 7:** Environment-aware code written
- [ ] **Rule 8:** Only requested changes made
- [ ] **Rule 9:** Existing solutions exhausted first
- [ ] **Rule 10:** Codebase kept clean and organized
- [ ] **Rule 11:** No one-time scripts in files
- [ ] **Rule 12:** File sizes under 200-300 lines
- [ ] **Rule 13:** No mock data in dev/prod
- [ ] **Rule 14:** No fake data patterns
- [ ] **Rule 15:** .env file not overwritten without permission
- [ ] **Rule 16:** Focused on relevant code areas
- [ ] **Rule 17:** No unrelated code touched
- [ ] **Rule 18:** Thorough tests written
- [ ] **Rule 19:** Working patterns preserved
- [ ] **Rule 20:** Impact on other areas considered

### **Platform-Specific:**
- [ ] Code runs in WSL2 Ubuntu 22.04
- [ ] Files stored in WSL2 filesystem (not /mnt/c/)
- [ ] GPU optimization enabled (FP16, gradient checkpointing)
- [ ] Docker containers use WSL2 backend
- [ ] CUDA environment variables set correctly

### **Data & API:**
- [ ] Using REAL data from databases
- [ ] Using REAL API calls (VALR, Claude, OpenAI)
- [ ] Trading mode checked before operations
- [ ] No hardcoded credentials
- [ ] Error handling for all external calls

### **Testing:**
- [ ] Unit tests written for new functions
- [ ] Integration tests for new endpoints
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] GPU tests pass if ML code (`pytest tests/ml/ -v`)

---

## 📁 PROJECT STRUCTURE

```
~/helios-v3/                           # ← WSL2 filesystem (FAST)
├── main.py                            # FastAPI application entry point
├── docker-compose.yml                 # Multi-container orchestration
├── Dockerfile                         # Container build instructions
├── requirements.txt                   # Python dependencies
├── .env                               # Environment variables (NEVER commit)
├── .env.example                       # Template for .env
├── HELIOS_V3_COMPLETE_PRD.md         # Complete product specification
├── CLAUDE.md                          # This file - AI coding guidelines
├── WINDOWS_11_WSL2_SETUP_SUMMARY.md  # WSL2 setup guide
│
├── src/                               # Source code
│   ├── api/                          # FastAPI routers and models
│   ├── trading/                      # Trading engine and orchestrator
│   ├── ml/                           # Neural network models and training
│   ├── llm/                          # LLM integration (Claude, GPT-4)
│   ├── risk/                         # GARCH volatility and risk metrics
│   ├── portfolio/                    # Portfolio manager (MPT, Black-Litterman)
│   ├── data/                         # Data ingestion and storage
│   └── utils/                        # Utility functions
│
├── tests/                             # Test suite
│   ├── test_api/                     # API endpoint tests
│   ├── test_trading/                 # Trading logic tests
│   ├── test_ml/                      # ML model tests
│   └── features/                     # BDD test scenarios (Gherkin)
│
├── models/                            # Trained model weights
│   └── neural_network_4060.pt        # Optimized for RTX 4060
│
├── database/                          # Database schemas and migrations
│   └── migrations/                   # Alembic migration scripts
│
├── helios-gui/                        # React GUI dashboard
│   ├── src/components/               # React components
│   └── package.json                  # Node.js dependencies
│
├── monitoring/                        # Prometheus and Grafana configs
│   ├── prometheus.yml
│   └── grafana/dashboards/
│
├── logs/                              # Application logs
└── data/                              # Data storage (InfluxDB exports, etc.)
```

---

## 🔍 FINDING EXISTING CODE

**Before writing ANY new code, search for existing implementations:**

```bash
# Search for class definitions
grep -rn "class PortfolioManager" src/

# Search for function implementations
grep -rn "def calculate_sharpe_ratio" src/

# Search for specific patterns
grep -rn "GARCH" src/

# Search for API endpoint definitions
grep -rn "@router.get" src/api/

# Search for database models
grep -rn "class.*Base" src/ | grep -i model
```

**If you find existing code:**
1. Read and understand it
2. Iterate on it rather than rewriting
3. Preserve the existing pattern
4. Only refactor if absolutely necessary

**If you don't find existing code:**
1. Check the PRD for specifications (`HELIOS_V3_COMPLETE_PRD.md`)
2. Implement it FULLY based on PRD
3. Follow existing patterns in similar modules
4. Write complete working code (NO PLACEHOLDERS)

---

## 🎯 REAL vs PLACEHOLDER CODE EXAMPLES

### **❌ WRONG - PLACEHOLDER CODE (NEVER DO THIS):**

```python
# VIOLATION: Placeholder implementation
def fetch_market_data(symbol: str):
    # TODO: implement VALR API call
    return {"price": 850000, "volume": 100}

# VIOLATION: Stub with NotImplementedError
class RiskEngine:
    def calculate_var(self):
        raise NotImplementedError("VaR calculation not implemented yet")

# VIOLATION: Hardcoded test data
def get_portfolio_value():
    # Temporary - replace with real DB query
    return 125430.50

# VIOLATION: Empty implementation
async def train_neural_network():
    pass  # Will implement after data pipeline is ready
```

### **✅ CORRECT - FULL IMPLEMENTATION:**

```python
# ✅ CORRECT - Full VALR API implementation
async def fetch_market_data(symbol: str) -> Dict[str, Any]:
    """
    Fetch real-time market data from VALR API.

    Args:
        symbol: Trading pair (e.g., 'BTCZAR')

    Returns:
        Dict with price, volume, timestamp

    Raises:
        APIError: If VALR API request fails
    """
    url = f"https://api.valr.com/v1/public/{symbol}/marketsummary"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    raise APIError(f"VALR API returned status {response.status}")

                data = await response.json()

                return {
                    "symbol": symbol,
                    "last_price": float(data["lastTradedPrice"]),
                    "bid_price": float(data["bidPrice"]),
                    "ask_price": float(data["askPrice"]),
                    "base_volume": float(data["baseVolume"]),
                    "quote_volume": float(data["quoteVolume"]),
                    "timestamp": datetime.utcnow()
                }
        except asyncio.TimeoutError:
            raise APIError(f"VALR API timeout for {symbol}")
        except aiohttp.ClientError as e:
            raise APIError(f"VALR API client error: {str(e)}")

# ✅ CORRECT - Full VaR implementation with real math
class RiskEngine:
    def __init__(self, db_session):
        self.db = db_session

    def calculate_var(self, portfolio_id: int, confidence: float = 0.95,
                      horizon_days: int = 1) -> float:
        """
        Calculate Value at Risk using historical simulation method.

        Args:
            portfolio_id: Portfolio identifier
            confidence: Confidence level (default 95%)
            horizon_days: Risk horizon in days

        Returns:
            VaR as a positive number (expected loss)
        """
        # Fetch historical returns from database
        returns = self.db.query(PortfolioReturn)\
            .filter(PortfolioReturn.portfolio_id == portfolio_id)\
            .order_by(PortfolioReturn.timestamp.desc())\
            .limit(252)  # 1 year of daily returns

        if not returns:
            raise ValueError(f"No return data for portfolio {portfolio_id}")

        # Convert to numpy array
        returns_array = np.array([r.daily_return for r in returns])

        # Scale to horizon
        scaled_returns = returns_array * np.sqrt(horizon_days)

        # Calculate VaR at specified confidence level
        var_percentile = (1 - confidence) * 100
        var = np.percentile(scaled_returns, var_percentile)

        # Return as positive number (expected loss)
        return abs(float(var))

# ✅ CORRECT - Real database query
async def get_portfolio_value(portfolio_id: int) -> float:
    """
    Get current portfolio value from database.

    Queries positions table and calculates total value based on
    current market prices.
    """
    async with get_db_session() as session:
        # Get all positions
        positions = await session.execute(
            select(Position).where(Position.portfolio_id == portfolio_id)
        )
        positions = positions.scalars().all()

        total_value = 0.0

        # Calculate value for each position
        for position in positions:
            # Get current market price
            current_price = await fetch_market_data(position.symbol)
            position_value = position.quantity * current_price["last_price"]
            total_value += position_value

        # Add cash balance
        portfolio = await session.get(Portfolio, portfolio_id)
        total_value += portfolio.cash_balance

        return float(total_value)

# ✅ CORRECT - Full neural network training implementation
async def train_neural_network(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    epochs: int = 10,
    device: str = "cuda"
) -> Dict[str, List[float]]:
    """
    Train neural network with full training loop.

    Includes: mixed precision, gradient checkpointing, validation,
    early stopping, model checkpointing.

    Returns:
        Dict with training history (loss, accuracy, val_loss, val_accuracy)
    """
    model = model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    criterion = nn.CrossEntropyLoss()
    scaler = torch.cuda.amp.GradScaler()  # Mixed precision

    history = {"loss": [], "accuracy": [], "val_loss": [], "val_accuracy": []}
    best_val_loss = float('inf')
    patience = 5
    patience_counter = 0

    for epoch in range(epochs):
        # Training phase
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for batch_idx, (features, targets) in enumerate(train_loader):
            features = features.to(device)
            targets = targets.to(device)

            optimizer.zero_grad()

            # Mixed precision forward pass
            with torch.cuda.amp.autocast():
                outputs = model(features)
                loss = criterion(outputs, targets)

            # Mixed precision backward pass
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            # Track metrics
            train_loss += loss.item()
            _, predicted = outputs.max(1)
            train_total += targets.size(0)
            train_correct += predicted.eq(targets).sum().item()

        # Calculate epoch metrics
        epoch_loss = train_loss / len(train_loader)
        epoch_acc = 100.0 * train_correct / train_total

        # Validation phase
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for features, targets in val_loader:
                features = features.to(device)
                targets = targets.to(device)

                with torch.cuda.amp.autocast():
                    outputs = model(features)
                    loss = criterion(outputs, targets)

                val_loss += loss.item()
                _, predicted = outputs.max(1)
                val_total += targets.size(0)
                val_correct += predicted.eq(targets).sum().item()

        val_epoch_loss = val_loss / len(val_loader)
        val_epoch_acc = 100.0 * val_correct / val_total

        # Save history
        history["loss"].append(epoch_loss)
        history["accuracy"].append(epoch_acc)
        history["val_loss"].append(val_epoch_loss)
        history["val_accuracy"].append(val_epoch_acc)

        logger.info(
            f"Epoch {epoch+1}/{epochs} - "
            f"Loss: {epoch_loss:.4f}, Acc: {epoch_acc:.2f}% - "
            f"Val Loss: {val_epoch_loss:.4f}, Val Acc: {val_epoch_acc:.2f}%"
        )

        # Early stopping
        if val_epoch_loss < best_val_loss:
            best_val_loss = val_epoch_loss
            patience_counter = 0
            # Save best model
            torch.save(model.state_dict(), "models/best_model.pt")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                logger.info(f"Early stopping triggered at epoch {epoch+1}")
                break

    return history
```

---

## 🔐 SECURITY & CREDENTIALS

### **Environment Variables (NEVER HARDCODE):**

```python
# ✅ CORRECT
import os
from dotenv import load_dotenv

load_dotenv()

VALR_API_KEY = os.getenv("VALR_API_KEY")
VALR_API_SECRET = os.getenv("VALR_API_SECRET")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not VALR_API_KEY:
    raise ValueError("VALR_API_KEY not found in environment")

# ❌ WRONG - NEVER DO THIS
VALR_API_KEY = "abc123xyz..."  # Hardcoded - SECURITY VIOLATION
```

### **.env File (NEVER COMMIT TO GIT):**

```bash
# .env (create this file, add to .gitignore)
POSTGRES_PASSWORD=your_secure_password
VALR_API_KEY=your_valr_api_key
VALR_API_SECRET=your_valr_secret
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...
TRADING_MODE=PAPER
```

---

## 📚 REFERENCE DOCUMENTS

1. **HELIOS_V3_COMPLETE_PRD.md** - Complete product specification (11,400+ lines)
   - Architecture details
   - API specifications
   - Database schemas
   - Feature implementations
   - GPU optimization configs

2. **WINDOWS_11_WSL2_SETUP_SUMMARY.md** - Platform setup guide
   - WSL2 installation
   - GPU configuration
   - Docker setup
   - Deployment instructions

3. **CLAUDE.md** (this file) - Coding guidelines and rules

---

## ⚡ QUICK REFERENCE COMMANDS

### **WSL2 Commands:**
```bash
# Check WSL version
wsl --list --verbose

# Restart WSL2
wsl --shutdown

# Check GPU in WSL2
nvidia-smi
```

### **Docker Commands:**
```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f helios-engine

# Check GPU in container
docker exec helios_engine nvidia-smi

# Restart specific service
docker-compose restart helios-engine
```

### **Testing Commands:**
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_portfolio.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run BDD tests
pytest tests/features/ -v
```

### **Server Commands:**
```bash
# Start FastAPI server (ASK USER FIRST!)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Check server health
curl http://localhost:8000/api/health

# Check trading mode
curl http://localhost:8000/api/orchestrator/system/trading/mode
```

---

## 🎓 WHEN IN DOUBT

1. **Check the PRD:** `HELIOS_V3_COMPLETE_PRD.md` has the specification
2. **Search existing code:** Use `grep` to find similar implementations
3. **Ask the user:** If unclear, STOP and ASK instead of guessing
4. **No placeholders:** If you can't implement completely, ask for help
5. **Test thoroughly:** Every change must be tested before completion

---

**REMEMBER: These rules are NON-NEGOTIABLE and form the foundation of all coding work on the Helios Trading System V3.0. Compliance is required for system safety, performance, and maintainability.**

**RULE ZERO IS ABSOLUTE: NEVER WRITE PLACEHOLDER CODE. EVERY FUNCTION MUST BE FULLY IMPLEMENTED WITH REAL LOGIC, REAL DATA, AND REAL CALCULATIONS.**

---

---

## 🔄 MODULAR ARCHITECTURE - BUILD THE PLANE WHILE FLYING

**NEW in v3.1.0:** Helios now supports hot-reloading, feature flags, circuit breakers, and safe module swapping.

### **Core Modularity Principles:**

1. **Hot-Reload Modules** - Update components without restarting the system
2. **Test Before Deploy** - Validate modules in isolation before going live
3. **Gradual Rollout** - Deploy features to X% of traffic incrementally
4. **Circuit Breakers** - Prevent cascading failures during updates
5. **Zero Downtime** - Swap modules on the fly safely

### **Quick Start - Modular Deployment:**

```python
from src.core import module_loader, feature_flags, circuit_breaker_manager

# 1. Register new module
await module_loader.register_module(
    name="neural_predictor_v2",
    module_path="src.ml.inference.neural_predictor_v2",
    version="2.0.0",
    hot_reloadable=True
)

# 2. Load and test
instance = await module_loader.load_module("neural_predictor_v2")
tester = module_testing_manager.create_tester("neural_predictor_v2", "ml")
if await tester.run_tests(instance):

    # 3. Enable for 10% of traffic
    await feature_flags.set_percentage("neural_network_v2", 10.0)

    # 4. Protect with circuit breaker
    breaker = await circuit_breaker_manager.get_or_create("neural_predictor")

    # 5. Monitor and gradually increase rollout
    # 25% → 50% → 100%
```

### **Modular Architecture Guidelines:**

**ALWAYS:**
- ✅ Test modules before deployment using `module_testing_manager`
- ✅ Use feature flags for new features (gradual rollout)
- ✅ Protect critical components with circuit breakers
- ✅ Register modules with proper dependencies
- ✅ Add reload hooks for post-reload initialization

**NEVER:**
- ❌ Deploy untested modules to production
- ❌ Hot-reload modules marked as `hot_reloadable=False`
- ❌ Skip circuit breakers for external API calls
- ❌ Deploy to 100% traffic immediately (use gradual rollout)

### **API Endpoints for Modularity:**

All modularity features available at `/api/modularity/*`:

```bash
# Module management
POST /api/modularity/modules/register
POST /api/modularity/modules/{name}/load
POST /api/modularity/modules/swap
POST /api/modularity/modules/{name}/test

# Feature flags
POST /api/modularity/feature-flags/enable
POST /api/modularity/feature-flags/percentage
GET  /api/modularity/feature-flags

# Circuit breakers
GET  /api/modularity/circuit-breakers
POST /api/modularity/circuit-breakers/{name}/reset
```

**See MODULAR_ARCHITECTURE_GUIDE.md for complete documentation.**

---

*Last Updated: January 16, 2025 - Version 3.1.0 - Windows 11 WSL2 + RTX 4060 + Modular Architecture*
*Added: Rule Zero (No Placeholders Ever), Platform-specific requirements, RTX 4060 optimizations*
