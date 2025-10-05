# Helios V3.0 - Windows 11 WSL2 Setup Summary

**Document Version:** 3.0.1
**Date:** January 16, 2025
**Platform:** Windows 11 + WSL2 Ubuntu 22.04 + RTX 4060

---

## ✅ What Was Modified

The HELIOS V3.0 PRD has been **fully optimized for Windows 11 with WSL2** and the **NVIDIA RTX 4060 GPU (8GB/12GB VRAM)**.

### **Key Changes:**

1. **Updated Platform Specification** (Header)
   - Primary platform changed from "Ubuntu 22.04 Server" to "Windows 11 + WSL2 Ubuntu 22.04"
   - RTX 4060 (8GB/12GB) designated as **PRIMARY TARGET GPU**

2. **New Section 46: Windows 11 WSL2 Setup** (~180 lines)
   - Complete 7-step setup instructions
   - WSL2 installation and configuration
   - NVIDIA Driver installation (Windows host)
   - Docker Desktop configuration for WSL2 backend
   - NVIDIA Container Toolkit installation
   - `.wslconfig` optimization guide
   - Project directory setup recommendations

3. **New: Windows 11 WSL2 Deployment Instructions** (~200 lines)
   - 7-step deployment guide specific to WSL2
   - Environment preparation with `.env` file
   - Docker Compose build and start
   - Database initialization
   - Historical data backfill
   - Auto-trading enablement (paper mode)
   - GUI dashboard access
   - Common WSL2 commands reference
   - Performance tuning for Windows 11
   - Troubleshooting guide for WSL2-specific issues

4. **Updated Section 52.7: Compatibility Requirements**
   - **New 52.7.1:** Operating System Compatibility table
     - Windows 11 + WSL2 marked as **PRIMARY PLATFORM**
   - **Updated 52.7.2:** Software Compatibility
     - Added platform column (WSL2/Ubuntu/Windows)
     - Added Docker Desktop, WSL2 version, NVIDIA Driver requirements
   - **New 52.7.3:** Hardware Compatibility
     - Comprehensive GPU compatibility matrix for Windows 11 WSL2
     - RTX 4060 8GB and 12GB both marked as PRIMARY TARGET
     - CPU compatibility matrix (Intel 12th/13th/14th Gen, AMD Ryzen 5000/7000)
     - RAM requirements table (32GB/64GB/128GB configurations)
     - Storage requirements breakdown

5. **New: Quick Start Guide** (Beginning of document)
   - 5-minute setup guide for Windows 11 + RTX 4060 users
   - Direct links to prerequisite downloads
   - Copy-paste commands for rapid deployment
   - Links to detailed setup in Section 46

6. **Updated Version History**
   - Version 3.0.1 added documenting Windows 11 WSL2 optimization

---

## 🖥️ Target Hardware Specifications

**Confirmed Optimal Configuration:**

```
Hardware Requirements:
├── GPU: NVIDIA RTX 4060 (8GB or 12GB VRAM) ✅ PRIMARY TARGET
├── CPU: 6+ Cores (Intel i5-12600K, AMD Ryzen 5 7600X or better)
├── RAM: 32GB DDR4/DDR5 minimum (64GB recommended)
├── Storage: 1TB NVMe SSD
└── Network: Gigabit Ethernet or Wi-Fi 6

Operating System:
├── Windows 11 (64-bit) Build 22000+
├── WSL2 enabled with Ubuntu 22.04 LTS
├── NVIDIA Game Ready Driver 535+
├── Docker Desktop for Windows (WSL2 backend)
└── Visual Studio Code (optional)
```

---

## 🚀 Quick Deployment Steps

### **1. Enable WSL2 (PowerShell as Admin)**
```powershell
wsl --install -d Ubuntu-22.04
# Reboot PC
```

### **2. Install NVIDIA Driver (Windows)**
- Download: https://www.nvidia.com/Download/index.aspx
- Install latest Game Ready Driver (535.x or higher)

### **3. Install Docker Desktop (Windows)**
- Download: https://www.docker.com/products/docker-desktop
- Enable WSL2 backend in Settings → General → "Use the WSL 2 based engine"

### **4. Configure WSL2**
Create `C:\Users\YourUsername\.wslconfig`:
```ini
[wsl2]
memory=24GB
processors=10
nestedVirtualization=true
swap=8GB
gpuSupport=true
```

Restart WSL2:
```powershell
wsl --shutdown
```

### **5. Install NVIDIA Container Toolkit (WSL2 Ubuntu)**
```bash
sudo apt update
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-docker2
```

Verify GPU access:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### **6. Deploy Helios V3.0**
```bash
cd ~
git clone https://github.com/yourusername/helios-v3.git
cd helios-v3

# Create .env file
cat > .env << 'EOF'
POSTGRES_PASSWORD=your_password
VALR_API_KEY=your_key
VALR_API_SECRET=your_secret
ANTHROPIC_API_KEY=your_claude_key
TRADING_MODE=PAPER
EOF

# Start services
docker-compose up -d

# Initialize database
docker exec helios_engine python3 -m alembic upgrade head

# Enable auto-trading
curl -X POST http://localhost:8000/api/orchestrator/auto-trading/enable
```

### **7. Access Dashboards**
- **API:** http://localhost:8000
- **Grafana:** http://localhost:3000
- **GUI:** http://localhost:3001
- **Prometheus:** http://localhost:9091

---

## 🔧 RTX 4060 GPU Optimizations

The PRD includes **complete GPU optimization** for the RTX 4060 8GB VRAM:

### **Memory Optimizations (Enabled by Default):**

1. **Mixed Precision Training (FP16):**
   ```python
   TRAINING_CONFIG_4060 = {
       'mixed_precision': True,  # Reduces memory by ~50%
   }
   ```

2. **Gradient Checkpointing:**
   ```python
   # Saves 40% VRAM at cost of 20% slower training
   'gradient_checkpointing': True,
   ```

3. **Optimized Batch Size:**
   ```python
   'batch_size': 16,  # Reduced from 32 for 8GB VRAM
   'accumulation_steps': 2,  # Effective batch size = 32
   ```

4. **CUDA Memory Management:**
   ```bash
   export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
   ```

### **Model Architecture (40M Parameters):**
- Optimized layer sizes for 8GB VRAM
- Gradient checkpointing hooks on LSTM layers
- FP16 automatic mixed precision
- Optimized for both 8GB and 12GB variants

---

## 📊 Performance Targets (Windows 11 WSL2 + RTX 4060)

| **Metric** | **Target** | **Load Condition** |
|------------|-----------|-------------------|
| Neural Inference Latency | < 200ms (P95) | Single prediction |
| Feature Engineering | < 50ms (P95) | 90 features |
| Trading Loop Cycle | < 5 seconds | End-to-end |
| GPU Memory Usage | < 7GB | Training (8GB model) |
| GPU Utilization | 20-60% | Normal operation |
| CPU Usage | < 80% | 6-core minimum |
| RAM Usage | < 24GB | 32GB total system |

---

## 🐛 Common WSL2 Troubleshooting

### **Issue: GPU not accessible in Docker**
```bash
# Solution: Reinstall NVIDIA Container Toolkit
sudo apt purge -y nvidia-docker2
sudo apt autoremove -y
sudo apt install -y nvidia-docker2
# Restart Docker Desktop
```

### **Issue: Docker daemon not starting**
```powershell
# In PowerShell as Admin
wsl --shutdown
# Restart Docker Desktop application
```

### **Issue: Out of memory errors**
```bash
# Free up Docker memory
docker system prune -a

# Increase WSL2 memory in .wslconfig
[wsl2]
memory=28GB
```

### **Issue: Slow file I/O**
```bash
# Move project to WSL2 filesystem (3-5× faster)
mv /mnt/c/helios-v3 ~/helios-v3
cd ~/helios-v3
```

### **Issue: nvidia-smi command not found in WSL2**
```bash
# Windows NVIDIA driver is shared - no need to install in WSL2
# Just verify driver is installed on Windows host
```

---

## 📁 Recommended File Structure

**For best performance, store files in WSL2 filesystem:**

```
~/helios-v3/                    # ← Store here (fast)
├── docker-compose.yml
├── Dockerfile
├── .env
├── requirements.txt
├── src/
├── models/
├── data/
└── helios-gui/

# NOT here (slow):
/mnt/c/Users/YourName/helios-v3/  # ← Avoid (Windows filesystem)
```

**Reason:** WSL2 native filesystem is 3-5× faster than accessing Windows filesystem via `/mnt/c/`.

---

## 🔍 Verification Checklist

After setup, verify:

- [ ] `wsl --list --verbose` shows Ubuntu-22.04 version 2
- [ ] `nvidia-smi` works in WSL2 Ubuntu terminal
- [ ] `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi` shows RTX 4060
- [ ] Docker Desktop shows "WSL 2 based engine" enabled
- [ ] `docker ps` shows 4 containers running (helios_engine, postgres, prometheus, grafana)
- [ ] `curl http://localhost:8000/api/health` returns `{"status":"healthy"}`
- [ ] Windows Task Manager shows GPU utilization when training
- [ ] Grafana dashboard accessible at http://localhost:3000

---

## 📖 Where to Find Details

All Windows 11 WSL2 specific information is located in:

- **Section 46:** Complete WSL2 setup instructions (7 steps)
- **Section 47:** Windows 11 WSL2 deployment guide (7 steps)
- **Section 52.7:** Compatibility requirements (OS, software, hardware)
- **Quick Start Guide:** 5-minute deployment (beginning of PRD)

---

## 🎯 Key Differences from Standard Ubuntu Deployment

| **Aspect** | **Standard Ubuntu** | **Windows 11 WSL2** |
|-----------|-------------------|-------------------|
| NVIDIA Driver | Install in Ubuntu | Install in Windows only |
| Docker | Native installation | Docker Desktop (WSL2 backend) |
| GPU Access | Direct | Via Windows driver passthrough |
| File System | Native ext4 | WSL2 filesystem (faster) or Windows NTFS (slower) |
| Networking | Direct | Port forwarding (localhost works) |
| Resource Limits | Physical hardware | Configured via `.wslconfig` |

---

## ✅ Production Readiness

The PRD is **fully production-ready for Windows 11 + WSL2 + RTX 4060** deployment:

✅ Complete setup instructions
✅ GPU optimization for 8GB VRAM
✅ Docker containerization with NVIDIA support
✅ Deployment automation scripts
✅ Performance tuning guidelines
✅ Troubleshooting guide
✅ Hardware compatibility matrix
✅ Resource allocation recommendations

---

**For complete details, refer to:**
`HELIOS_V3_COMPLETE_PRD.md` - Sections 46, 47, and 52.7

**Version:** 3.0.1 - Windows 11 WSL2 Optimized
**Last Updated:** January 16, 2025
