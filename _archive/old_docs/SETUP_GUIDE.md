# Helios Trading System V3.0 - Complete Setup Guide

> **Step-by-step guide to install and configure Helios V3.0**

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Steps](#installation-steps)
3. [Database Setup](#database-setup)
4. [Configuration](#configuration)
5. [Testing](#testing)
6. [Starting the System](#starting-the-system)
7. [Verification](#verification)
8. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### **Required Software:**

✅ **Python 3.10 or higher**
```bash
python --version  # Should be 3.10+
```

✅ **PostgreSQL 14 or higher**
```bash
psql --version  # Should be 14+
```

✅ **Redis 7 or higher**
```bash
redis-cli --version  # Should be 7+
```

✅ **InfluxDB 2.0 or higher**
```bash
influx version  # Should be 2.0+
```

### **Optional (for ML training):**

✅ **NVIDIA GPU** (RTX 4060 recommended)
```bash
nvidia-smi  # Check GPU is detected
```

✅ **CUDA 12.1+**
```bash
nvcc --version  # Check CUDA version
```

---

## 2. Installation Steps

### **Step 1: Clone Repository**
```bash
git clone <your-repo-url> helios-v3
cd helios-v3
```

### **Step 2: Create Virtual Environment**
```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/WSL2)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate.bat
```

### **Step 3: Install Dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### **Step 4: Create Environment File**
```bash
cp .env.example .env
```

---

## 3. Database Setup

### **PostgreSQL Setup**

#### **Step 1: Install PostgreSQL** (if not installed)
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### **Step 2: Create Database and User**
```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL prompt:
CREATE USER helios WITH PASSWORD 'your_secure_password_here';
CREATE DATABASE helios_v3 OWNER helios;
GRANT ALL PRIVILEGES ON DATABASE helios_v3 TO helios;
\q
```

#### **Step 3: Run Database Schema**
```bash
# Run schema file
psql -U helios -d helios_v3 -f database/schema.sql

# Verify tables created
psql -U helios -d helios_v3 -c "\dt"
```

### **Redis Setup**

#### **Install Redis** (if not installed)
```bash
# Ubuntu/Debian
sudo apt install redis-server

# Start service
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test connection
redis-cli ping  # Should return PONG
```

### **InfluxDB Setup**

#### **Install InfluxDB** (if not installed)
```bash
# Ubuntu/Debian
wget https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.4-amd64.deb
sudo dpkg -i influxdb2-2.7.4-amd64.deb

# Start service
sudo systemctl start influxdb
sudo systemctl enable influxdb

# Setup (follow web UI at http://localhost:8086)
```

#### **Create InfluxDB Token**
1. Open http://localhost:8086
2. Login with your credentials
3. Go to **Data > Tokens**
4. Click **Generate Token**
5. Copy the token to `.env` file

---

## 4. Configuration

### **Edit .env File**

Open `.env` in your editor and configure:

```bash
# ============================================================
# CRITICAL: Configure these before starting
# ============================================================

# Database
POSTGRES_PASSWORD=your_secure_password_here

# VALR API (get from https://www.valr.com/settings/api)
VALR_API_KEY=your_valr_api_key_here
VALR_API_SECRET=your_valr_api_secret_here

# LLM (get from https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# InfluxDB
INFLUX_TOKEN=your_influx_token_here

# ============================================================
# OPTIONAL: Adjust as needed
# ============================================================

# Trading Mode
TRADING_MODE=paper  # Start with paper trading!

# Feature Flags
ENABLE_AUTO_TRADING=false  # Keep disabled initially
ENABLE_ML_PREDICTIONS=true
ENABLE_LLM_ANALYSIS=true

# Risk Limits
MAX_POSITION_SIZE_PCT=0.20  # 20% max
MAX_LEVERAGE=3.0
MAX_DRAWDOWN_PCT=0.15  # -15% stop
DAILY_LOSS_LIMIT_PCT=0.05  # -5% daily limit

# ML Configuration (RTX 4060 optimized)
ML_BATCH_SIZE=16
ML_MIXED_PRECISION=true
ML_GRADIENT_CHECKPOINTING=true
ML_DEVICE=cuda  # or 'cpu' if no GPU

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### **Important Configuration Notes:**

⚠️ **ALWAYS start with `TRADING_MODE=paper`**
⚠️ **Keep `ENABLE_AUTO_TRADING=false` until system is fully tested**
⚠️ **Test all features in paper mode first**

---

## 5. Testing

### **Step 1: Test Modular Architecture**
```bash
python test_modularity.py
```

**Expected output:**
```
=============================================================
  HELIOS V3.0 - MODULAR ARCHITECTURE TEST SUITE
=============================================================

Testing Module Loader
✓ Module loaded successfully
✓ Module status: {...}
✓ Module Loader tests passed!

Testing Feature Flags
✓ Default feature flags loaded: 8
  - auto_trading: DISABLED
  - neural_network_v2: DISABLED
  - llm_strategic_analysis: ENABLED
  - garch_volatility: ENABLED
  - kelly_position_sizing: ENABLED
  - black_litterman: DISABLED
  - websocket_streaming: ENABLED
  - circuit_breakers: ENABLED
✓ Feature Flags tests passed!

Testing Circuit Breakers
✓ Circuit breaker created
✓ Circuit breaker status: closed
✓ Circuit Breaker tests passed!

Testing Module Testing Framework
✓ Module tester created
✓ Tests completed: 2/2 passed
✓ Module Testing Framework tests passed!

=============================================================
  ✓ ALL TESTS PASSED!
=============================================================
```

### **Step 2: Test Database Connection**
```bash
python -c "
import asyncio
from src.api.dependencies import initialize_services, cleanup_services

async def test():
    await initialize_services()
    print('✓ Database connections successful!')
    await cleanup_services()

asyncio.run(test())
"
```

---

## 6. Starting the System

### **Method 1: Using Startup Script**

#### **Linux/WSL2:**
```bash
chmod +x start_v3.sh
./start_v3.sh
```

#### **Windows:**
```bash
start_v3.bat
```

### **Method 2: Manual Start**
```bash
python main_v3.py
```

### **Expected Startup Output:**
```
============================================================
🚀 Starting Helios Trading System V3.0
============================================================

Initializing database services...
✓ Database services initialized

Initializing modular architecture...
  ✓ Circuit breaker created: valr_api
  ✓ Circuit breaker created: postgres_db
  ✓ Circuit breaker created: redis_cache
  ✓ Circuit breaker created: neural_network
  ✓ Circuit breaker created: llm_api
✓ Modular architecture initialized

Environment: development
Trading Mode: paper
Auto-trading: DISABLED
ML Predictions: ENABLED
LLM Analysis: ENABLED

============================================================
✓ Helios Trading System V3.0 is ready
============================================================

INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 7. Verification

### **Step 1: Check Health**
```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-16T10:30:00.000000",
  "version": "3.1.0"
}
```

### **Step 2: Check System Info**
```bash
curl http://localhost:8000/api/system/info
```

### **Step 3: Check Modularity Status**
```bash
curl http://localhost:8000/api/modularity/status
```

### **Step 4: Open API Documentation**

Open browser:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### **Step 5: Test Feature Flags**
```bash
# Get all feature flags
curl http://localhost:8000/api/modularity/feature-flags

# Check specific flag
curl http://localhost:8000/api/modularity/feature-flags/llm_strategic_analysis
```

### **Step 6: Test Circuit Breakers**
```bash
# Get all circuit breakers
curl http://localhost:8000/api/modularity/circuit-breakers

# Check specific breaker
curl http://localhost:8000/api/modularity/circuit-breakers/valr_api
```

---

## 8. Troubleshooting

### **Issue: Database Connection Failed**

**Error:** `connection to server at "localhost" (::1), port 5432 failed`

**Solution:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# If not running:
sudo systemctl start postgresql

# Check credentials
psql -U helios -d helios_v3 -c "SELECT 1"
```

### **Issue: Redis Connection Failed**

**Error:** `Error connecting to Redis`

**Solution:**
```bash
# Check Redis is running
sudo systemctl status redis-server

# If not running:
sudo systemctl start redis-server

# Test connection
redis-cli ping
```

### **Issue: Module Import Errors**

**Error:** `ModuleNotFoundError: No module named 'src'`

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # Linux/WSL2
# or
venv\Scripts\activate.bat  # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### **Issue: GPU Not Detected**

**Error:** `CUDA not available`

**Solution:**
```bash
# Check NVIDIA driver
nvidia-smi

# Check PyTorch GPU support
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# If False, set ML_DEVICE=cpu in .env
```

### **Issue: Permission Denied on Scripts**

**Error:** `Permission denied: ./start_v3.sh`

**Solution:**
```bash
chmod +x start_v3.sh
chmod +x database/setup_db.sh
```

### **Issue: Port Already in Use**

**Error:** `Address already in use`

**Solution:**
```bash
# Find process using port 8000
lsof -i :8000  # Linux/WSL2
netstat -ano | findstr :8000  # Windows

# Kill process or change PORT in .env
```

---

## 🎯 Next Steps

After successful setup:

1. ✅ **Verify all tests pass:** `python test_modularity.py`
2. ✅ **Start in paper mode:** `TRADING_MODE=paper`
3. ✅ **Test all API endpoints:** Use Swagger UI
4. ✅ **Monitor logs:** Check `logs/` directory
5. ✅ **Gradual feature rollout:** Use feature flags API
6. ✅ **Only enable live trading after thorough testing**

---

## 📞 Need Help?

- **Documentation:** See `README_V3.md`
- **PRD:** See `HELIOS_V3_COMPLETE_PRD.md`
- **Coding Guidelines:** See `CLAUDE.md`
- **Logs:** Check `logs/helios.log`

---

**Congratulations! Your Helios Trading System V3.0 is now set up! 🎉**
