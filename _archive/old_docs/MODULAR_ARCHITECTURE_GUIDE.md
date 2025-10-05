# Helios V3.0 - Modular Architecture Guide
## Build the Plane While Flying

**Version:** 1.0.0
**Date:** January 2025
**Purpose:** Hot-reload, incremental deployment, and safe module swapping

---

## 🎯 Overview

The Helios modular architecture enables you to:

- **Hot-reload modules** without restarting the entire system
- **Test new features** in isolation before deployment
- **Gradual rollout** of features with percentage-based deployment
- **Circuit breakers** to prevent cascading failures
- **Zero-downtime updates** by swapping modules on the fly

---

## 🏗️ Core Components

### 1. Module Loader (`src/core/module_loader.py`)

Dynamic module loading and hot-reloading system.

**Key Features:**
- Load/unload modules at runtime
- Dependency management
- Hot-swap with rollback on failure
- Module state tracking (unloaded/loading/loaded/active/failed)

**Example Usage:**
```python
from src.core import module_loader

# Register a module
await module_loader.register_module(
    name="paper_trading_v2",
    module_path="src.trading.services.paper_trading_v2",
    version="2.0.0",
    dependencies=["market_simulator"],
    hot_reloadable=True
)

# Load the module
instance = await module_loader.load_module("paper_trading_v2")

# Hot-swap to new version
success = await module_loader.swap_module(
    "paper_trading_v2",
    new_version_path="src.trading.services.paper_trading_v3"
)

# Check status
status = module_loader.get_module_status("paper_trading_v2")
```

### 2. Feature Flags (`src/core/feature_flags.py`)

Control feature availability at runtime with multiple rollout strategies.

**Rollout Strategies:**
- `ALL_ON` - Feature enabled for everyone
- `ALL_OFF` - Feature disabled for everyone
- `PERCENTAGE` - Enable for X% of traffic (deterministic based on session)
- `WHITELIST` - Enable for specific users/symbols/systems
- `GRADUAL` - Time-based percentage increase

**Example Usage:**
```python
from src.core import feature_flags

# Initialize (auto-loads config/feature_flags.json)
await feature_flags.initialize()

# Check if feature is enabled
if await feature_flags.is_enabled("neural_network_v2"):
    # Use new neural network
    predictor = NeuralNetworkV2()
else:
    # Use legacy neural network
    predictor = NeuralNetworkV1()

# Enable feature for 25% of traffic
await feature_flags.set_percentage("websocket_v2", 25.0)

# Enable for specific symbol
await feature_flags.add_to_whitelist("advanced_risk_engine", "BTCZAR")

# Full rollout
await feature_flags.enable_flag("multi_timeframe_analysis", RolloutStrategy.ALL_ON)
```

### 3. Circuit Breakers (`src/core/circuit_breaker.py`)

Protect system during module updates and isolate failures.

**States:**
- `CLOSED` - Normal operation
- `OPEN` - Failure detected, requests blocked
- `HALF_OPEN` - Testing if service recovered

**Example Usage:**
```python
from src.core import circuit_breaker_manager, CircuitBreakerConfig

# Get or create circuit breaker
breaker = await circuit_breaker_manager.get_or_create(
    "neural_predictor",
    config=CircuitBreakerConfig(
        failure_threshold=5,
        timeout=60.0,
        success_threshold=2
    )
)

# Protected execution
async def make_prediction(data):
    return await breaker.call(neural_predictor.predict, data)

# Fallback on failure
async def fallback_prediction(data):
    return {"prediction": "neutral", "confidence": 0.5}

breaker_with_fallback = CircuitBreaker(
    "neural_predictor",
    fallback=fallback_prediction
)

# Manual control
await breaker.manual_reset()  # Force close circuit
await breaker.manual_open()   # Force open circuit
```

### 4. Module Testing (`src/core/module_testing.py`)

Test modules in isolation before deployment.

**Pre-built Test Suites:**
- Trading services
- ML models
- Data pipelines

**Example Usage:**
```python
from src.core import module_testing_manager, ModuleTestSuite

# Create tester for trading service
tester = ModuleTestSuite.create_trading_service_tests("paper_trading_v2")

# Add custom test
async def test_order_execution(instance):
    result = await instance.place_order(test_order)
    return result.status == "filled"

tester.add_test(
    "order_execution",
    test_order_execution,
    required=True,
    timeout=10.0
)

# Run tests
module_instance = await module_loader.load_module("paper_trading_v2")
all_passed = await tester.run_tests(module_instance)

# Get report
report = tester.get_test_report()
print(f"Tests passed: {report['results']['passed']}/{report['total_tests']}")
```

---

## 🚀 API Endpoints

All modularity features are accessible via REST API at `/api/modularity/*`

### Module Management

```bash
# Get all module statuses
GET /api/modularity/modules/status

# Get specific module status
GET /api/modularity/modules/{module_name}/status

# Register new module
POST /api/modularity/modules/register
{
  "name": "paper_trading_v2",
  "module_path": "src.trading.services.paper_trading_v2",
  "version": "2.0.0",
  "dependencies": ["market_simulator"],
  "hot_reloadable": true
}

# Load module
POST /api/modularity/modules/{module_name}/load?force_reload=false

# Unload module
POST /api/modularity/modules/{module_name}/unload

# Hot-swap module
POST /api/modularity/modules/swap
{
  "name": "paper_trading_v2",
  "new_version_path": "src.trading.services.paper_trading_v3"
}
```

### Feature Flags

```bash
# Get all feature flags
GET /api/modularity/feature-flags

# Check if feature is enabled
GET /api/modularity/feature-flags/{flag_name}?context={"session_id":"abc123"}

# Enable feature flag
POST /api/modularity/feature-flags/enable
{
  "name": "neural_network_v2",
  "enabled": true,
  "strategy": "percentage"
}

# Set rollout percentage
POST /api/modularity/feature-flags/percentage
{
  "name": "neural_network_v2",
  "percentage": 25.0
}

# Disable feature
POST /api/modularity/feature-flags/disable?name=neural_network_v2
```

### Circuit Breakers

```bash
# Get all circuit breaker statuses
GET /api/modularity/circuit-breakers

# Reset specific circuit breaker
POST /api/modularity/circuit-breakers/{breaker_name}/reset

# Reset all circuit breakers
POST /api/modularity/circuit-breakers/reset-all
```

### Module Testing

```bash
# Test a module
POST /api/modularity/modules/{module_name}/test?module_type=trading

# Get test history
GET /api/modularity/modules/{module_name}/test-history

# Overall modularity status
GET /api/modularity/status
```

---

## 📋 Deployment Workflow

### Scenario: Deploy New Neural Network Version

**Step 1: Register the new module**
```bash
curl -X POST http://localhost:8000/api/modularity/modules/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "neural_predictor_v2",
    "module_path": "src.ml.inference.neural_predictor_v2",
    "version": "2.0.0",
    "dependencies": ["feature_extractor"],
    "hot_reloadable": true
  }'
```

**Step 2: Load and test the module**
```bash
# Load module
curl -X POST http://localhost:8000/api/modularity/modules/neural_predictor_v2/load

# Test module
curl -X POST http://localhost:8000/api/modularity/modules/neural_predictor_v2/test?module_type=ml
```

**Step 3: Create feature flag for gradual rollout**
```bash
# Enable for 10% of traffic
curl -X POST http://localhost:8000/api/modularity/feature-flags/percentage \
  -H "Content-Type: application/json" \
  -d '{
    "name": "neural_network_v2",
    "percentage": 10.0
  }'
```

**Step 4: Monitor circuit breaker**
```bash
curl http://localhost:8000/api/modularity/circuit-breakers
```

**Step 5: Gradually increase rollout**
```bash
# 25%
curl -X POST http://localhost:8000/api/modularity/feature-flags/percentage \
  -d '{"name": "neural_network_v2", "percentage": 25.0}'

# 50%
curl -X POST http://localhost:8000/api/modularity/feature-flags/percentage \
  -d '{"name": "neural_network_v2", "percentage": 50.0}'

# 100% (full rollout)
curl -X POST http://localhost:8000/api/modularity/feature-flags/enable \
  -d '{"name": "neural_network_v2", "enabled": true, "strategy": "all_on"}'
```

**Step 6: Hot-swap old module (if needed)**
```bash
curl -X POST http://localhost:8000/api/modularity/modules/swap \
  -H "Content-Type: application/json" \
  -d '{
    "name": "neural_predictor",
    "new_version_path": "src.ml.inference.neural_predictor_v2"
  }'
```

---

## 🔧 Integration Examples

### Example 1: Feature Flag in Trading Code

```python
from src.core import feature_flags

async def execute_trade(order_request):
    # Check which version to use
    if await feature_flags.is_enabled("paper_trading_v2"):
        # Use new version
        from src.trading.services.paper_trading_v2 import PaperTradingServiceV2
        service = PaperTradingServiceV2()
    else:
        # Use legacy version
        from src.trading.services.paper_trading_service import PaperTradingService
        service = PaperTradingService()

    return await service.place_order(order_request)
```

### Example 2: Circuit Breaker for ML Predictions

```python
from src.core import circuit_breaker_manager

async def get_ai_prediction(market_data):
    # Get circuit breaker for neural predictor
    breaker = await circuit_breaker_manager.get_or_create("neural_predictor")

    try:
        # Protected execution
        prediction = await breaker.call(
            neural_predictor.predict,
            market_data
        )
        return prediction
    except CircuitBreakerError:
        # Circuit is open, use fallback
        logger.warning("Neural predictor circuit open, using simple fallback")
        return simple_predictor.predict(market_data)
```

### Example 3: Module Hot-Reload Hook

```python
from src.core import module_loader

async def on_predictor_reload(new_instance):
    """Hook called after neural predictor is reloaded"""
    logger.info("Neural predictor reloaded, warming up cache...")

    # Warm up the new model
    test_data = get_sample_market_data()
    await new_instance.predict(test_data)

    logger.info("New predictor ready for production")

# Register hook
module_loader.add_reload_hook("neural_predictor", on_predictor_reload)
```

---

## 📊 Default Feature Flags

The system comes with these pre-configured feature flags:

| Flag | Default | Strategy | Description |
|------|---------|----------|-------------|
| `neural_network_v2` | OFF | PERCENTAGE | New neural network architecture |
| `llm_enhanced_decisions` | ON | ALL_ON | LLM-powered trading decisions |
| `paper_trading_v2` | OFF | GRADUAL (10%) | Enhanced paper trading |
| `advanced_risk_engine` | OFF | WHITELIST | Advanced risk management |
| `multi_timeframe_analysis` | ON | ALL_ON | Multi-timeframe analysis |
| `websocket_v2` | OFF | PERCENTAGE (25%) | New WebSocket implementation |
| `portfolio_optimizer_v2` | OFF | ALL_OFF | Advanced portfolio optimization |
| `hot_reload_modules` | ON | ALL_ON | Enable module hot-reloading |

---

## ⚠️ Best Practices

### 1. Always Test Before Deploying
```python
# WRONG - Deploy without testing
await module_loader.swap_module("critical_component")

# RIGHT - Test first
tester = module_testing_manager.create_tester("critical_component", "trading")
if await tester.run_tests(module_instance):
    await module_loader.swap_module("critical_component")
else:
    logger.error("Tests failed, aborting deployment")
```

### 2. Use Circuit Breakers for External Dependencies
```python
# Protect VALR API calls
valr_breaker = await circuit_breaker_manager.get_or_create("valr_api")
response = await valr_breaker.call(valr_client.get_market_data)
```

### 3. Gradual Rollout for Risky Changes
```python
# Start at 1%
await feature_flags.set_percentage("risky_feature", 1.0)

# Monitor for 1 hour, then increase to 10%
await asyncio.sleep(3600)
await feature_flags.set_percentage("risky_feature", 10.0)

# Continue gradual increase...
```

### 4. Rollback Strategy
```python
# If new version fails, immediately rollback
try:
    await module_loader.swap_module("trading_engine", "src.trading.engine_v2")
except Exception as e:
    logger.error(f"Swap failed: {e}, rolling back")
    await feature_flags.disable_flag("trading_engine_v2")
    await module_loader.swap_module("trading_engine", "src.trading.engine_v1")
```

---

## 🐛 Troubleshooting

### Module Won't Load
```bash
# Check module status
curl http://localhost:8000/api/modularity/modules/my_module/status

# Check dependencies
# Ensure all dependencies are loaded first

# Check error logs
# Look for import errors or initialization failures
```

### Circuit Breaker Stuck Open
```bash
# Check breaker status
curl http://localhost:8000/api/modularity/circuit-breakers

# Manual reset if safe
curl -X POST http://localhost:8000/api/modularity/circuit-breakers/my_breaker/reset
```

### Feature Flag Not Working
```bash
# Verify flag exists
curl http://localhost:8000/api/modularity/feature-flags

# Check context matches whitelist/percentage logic
curl "http://localhost:8000/api/modularity/feature-flags/my_flag?context={\"session_id\":\"test\"}"

# Reload flag configuration
await feature_flags.load_from_file()
```

---

## 📝 Configuration Files

### Feature Flags Configuration
**Location:** `config/feature_flags.json`

```json
{
  "neural_network_v2": {
    "enabled": false,
    "strategy": "percentage",
    "percentage": 25.0,
    "description": "New neural network architecture",
    "updated_at": "2025-01-16T10:00:00Z"
  },
  "llm_enhanced_decisions": {
    "enabled": true,
    "strategy": "all_on",
    "description": "LLM-powered decisions",
    "updated_at": "2025-01-16T10:00:00Z"
  }
}
```

---

## 🎯 Summary

The Helios modular architecture enables true "build the plane while flying" capabilities:

✅ **Hot-reload modules** without downtime
✅ **Test in isolation** before deployment
✅ **Gradual rollout** with percentage-based deployment
✅ **Circuit breakers** prevent cascading failures
✅ **Feature flags** control availability
✅ **Zero-downtime updates** via module swapping

Use the `/api/modularity` endpoints to manage all aspects of the modular system at runtime.

---

**For questions or issues, check logs at:** `logs/module_loader.log`, `logs/feature_flags.log`, `logs/circuit_breaker.log`
