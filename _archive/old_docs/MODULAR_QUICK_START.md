# Helios V3.0 - Modular Architecture Quick Start

**⚡ Get started with "build the plane while flying" in 5 minutes**

---

## 🎯 What You Can Do Now

- ✅ **Hot-reload modules** without restarting
- ✅ **Test changes** before deployment
- ✅ **Gradual rollout** (1% → 100%)
- ✅ **Circuit breakers** prevent failures
- ✅ **Zero downtime** updates

---

## 🚀 Quick Start (3 Steps)

### Step 1: Check Feature Flags
```bash
curl http://localhost:8000/api/modularity/feature-flags
```

### Step 2: Enable a Feature
```bash
# Enable for 25% of traffic
curl -X POST http://localhost:8000/api/modularity/feature-flags/percentage \
  -H "Content-Type: application/json" \
  -d '{"name": "neural_network_v2", "percentage": 25.0}'
```

### Step 3: Monitor Circuit Breakers
```bash
curl http://localhost:8000/api/modularity/circuit-breakers
```

---

## 📦 Deploy New Module (Full Workflow)

```bash
# 1. Register module
curl -X POST http://localhost:8000/api/modularity/modules/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_new_feature",
    "module_path": "src.features.my_new_feature",
    "version": "2.0.0",
    "hot_reloadable": true
  }'

# 2. Load module
curl -X POST http://localhost:8000/api/modularity/modules/my_new_feature/load

# 3. Test module
curl -X POST http://localhost:8000/api/modularity/modules/my_new_feature/test?module_type=generic

# 4. Enable for 10% traffic
curl -X POST http://localhost:8000/api/modularity/feature-flags/percentage \
  -H "Content-Type: application/json" \
  -d '{"name": "my_new_feature", "percentage": 10.0}'

# 5. Monitor for issues, then increase to 50%
curl -X POST http://localhost:8000/api/modularity/feature-flags/percentage \
  -H "Content-Type: application/json" \
  -d '{"name": "my_new_feature", "percentage": 50.0}'

# 6. Full rollout (100%)
curl -X POST http://localhost:8000/api/modularity/feature-flags/enable \
  -H "Content-Type: application/json" \
  -d '{"name": "my_new_feature", "enabled": true, "strategy": "all_on"}'
```

---

## 💻 Use in Python Code

### Feature Flag Example
```python
from src.core import feature_flags

async def process_trade(order):
    # Check which version to use
    if await feature_flags.is_enabled("new_trading_engine"):
        # Use new version
        result = await new_engine.execute(order)
    else:
        # Use legacy version
        result = await old_engine.execute(order)

    return result
```

### Circuit Breaker Example
```python
from src.core import circuit_breaker_manager

async def fetch_market_data(symbol):
    # Create circuit breaker
    breaker = await circuit_breaker_manager.get_or_create("valr_api")

    try:
        # Protected API call
        data = await breaker.call(valr_client.get_market_data, symbol)
        return data
    except CircuitBreakerError:
        # Fallback when circuit is open
        return get_cached_data(symbol)
```

### Module Hot-Swap Example
```python
from src.core import module_loader

async def update_predictor():
    # Test new version
    tester = module_testing_manager.create_tester("predictor_v2", "ml")
    if await tester.run_tests(new_instance):
        # Swap to new version
        await module_loader.swap_module("predictor", "src.ml.predictor_v2")
        print("✅ Predictor updated successfully")
    else:
        print("❌ Tests failed, keeping old version")
```

---

## 🛠️ Common Tasks

### Check System Status
```bash
curl http://localhost:8000/api/modularity/status
```

### List All Modules
```bash
curl http://localhost:8000/api/modularity/modules/status
```

### Reset Circuit Breaker
```bash
curl -X POST http://localhost:8000/api/modularity/circuit-breakers/my_breaker/reset
```

### Disable Feature Flag
```bash
curl -X POST "http://localhost:8000/api/modularity/feature-flags/disable?name=my_feature"
```

### View Test History
```bash
curl http://localhost:8000/api/modularity/modules/my_module/test-history
```

---

## 🔧 Pre-Configured Feature Flags

| Flag | Status | Strategy | Description |
|------|--------|----------|-------------|
| `neural_network_v2` | 🔴 OFF | Percentage | New neural network |
| `llm_enhanced_decisions` | 🟢 ON | All Users | LLM decisions |
| `paper_trading_v2` | 🔴 OFF | Gradual 10% | Enhanced paper trading |
| `advanced_risk_engine` | 🔴 OFF | Whitelist | Advanced risk mgmt |
| `multi_timeframe_analysis` | 🟢 ON | All Users | Multi-timeframe TA |
| `websocket_v2` | 🔴 OFF | 25% Rollout | New WebSocket |
| `portfolio_optimizer_v2` | 🔴 OFF | Disabled | Advanced optimizer |
| `hot_reload_modules` | 🟢 ON | All Users | Hot-reload enabled |

---

## 🎓 Run Examples

```bash
# Run comprehensive examples
python example_modular_deployment.py
```

This will demonstrate:
1. ✅ Full deployment workflow
2. ✅ Hot-swap module
3. ✅ Feature flag usage
4. ✅ Circuit breaker protection

---

## 📚 Full Documentation

- **Complete Guide:** `MODULAR_ARCHITECTURE_GUIDE.md`
- **Implementation Details:** `MODULARITY_IMPLEMENTATION_SUMMARY.md`
- **Coding Guidelines:** `CLAUDE.md` (Rule 0.5)

---

## ⚡ API Endpoints Reference

**Module Management:**
- `POST /api/modularity/modules/register` - Register new module
- `POST /api/modularity/modules/{name}/load` - Load module
- `POST /api/modularity/modules/swap` - Hot-swap module
- `POST /api/modularity/modules/{name}/test` - Test module

**Feature Flags:**
- `GET /api/modularity/feature-flags` - List all flags
- `POST /api/modularity/feature-flags/enable` - Enable flag
- `POST /api/modularity/feature-flags/percentage` - Set rollout %
- `POST /api/modularity/feature-flags/disable` - Disable flag

**Circuit Breakers:**
- `GET /api/modularity/circuit-breakers` - List all breakers
- `POST /api/modularity/circuit-breakers/{name}/reset` - Reset breaker
- `POST /api/modularity/circuit-breakers/reset-all` - Reset all

**Testing:**
- `POST /api/modularity/modules/{name}/test` - Run tests
- `GET /api/modularity/modules/{name}/test-history` - View history

---

## 🚨 Best Practices

**DO:**
- ✅ Test before deploying
- ✅ Start with low percentage (1-10%)
- ✅ Monitor circuit breakers
- ✅ Use gradual rollout for risky changes
- ✅ Have rollback plan ready

**DON'T:**
- ❌ Deploy untested modules
- ❌ Go 0% → 100% immediately
- ❌ Ignore circuit breaker warnings
- ❌ Hot-reload critical components without testing

---

## 🐛 Troubleshooting

**Module won't load?**
```bash
# Check status and error message
curl http://localhost:8000/api/modularity/modules/my_module/status
```

**Circuit breaker stuck open?**
```bash
# Reset if safe
curl -X POST http://localhost:8000/api/modularity/circuit-breakers/my_breaker/reset
```

**Feature flag not working?**
```bash
# Verify configuration
curl http://localhost:8000/api/modularity/feature-flags/my_flag
```

---

## 💡 Tips

1. **Start Small** - Test with 1% traffic first
2. **Monitor Metrics** - Watch circuit breaker success rates
3. **Gradual Increase** - Double percentage each step (1% → 2% → 5% → 10% → 25% → 50% → 100%)
4. **Quick Rollback** - Disable flag immediately if issues arise
5. **Test Everything** - Always run tests before hot-swap

---

**Ready to build the plane while flying! 🚀**

For detailed documentation, see `MODULAR_ARCHITECTURE_GUIDE.md`
