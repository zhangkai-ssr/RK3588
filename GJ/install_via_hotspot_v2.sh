#!/bin/bash
LOG=/tmp/install_via_hotspot.log
exec >> "$LOG" 2>&1
echo
echo "=========================================="
echo "=== $(date) RETRY with Tsinghua mirror ==="
echo "=========================================="

# Switch to S50
echo "[Step 1] Switching to S50..."
sudo nmcli connection down CYZX05 2>&1 || true
sleep 2
sudo nmcli connection up S50
if [ $? -ne 0 ]; then
    echo "[ERROR] S50 connect failed, rolling back"
    sudo nmcli connection up CYZX05 || true
    exit 1
fi
sleep 4
ip -4 -br a show wlP2p33s0

# Backup and switch sources to Tsinghua
echo "[Step 2] Switching apt sources to Tsinghua..."
sudo cp /etc/apt/sources.list /etc/apt/sources.list.bak.$(date +%s) 2>/dev/null || true
sudo tee /etc/apt/sources.list <<'EOF'
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-updates main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-backports main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-security main restricted universe multiverse
EOF

# Verify connectivity to Tsinghua
echo "[Step 3] Testing Tsinghua reachability..."
curl -sI -m 10 https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ | head -3

# apt update
echo "[Step 4] apt update..."
sudo apt-get update 2>&1 | tail -10

# apt install
echo "[Step 5] apt install..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --fix-missing \
    python3-pip python3-numpy python3-scipy cmake tcpdump 2>&1 | tail -30
APT_RC=${PIPESTATUS[0]}
echo "[Step 5] exit code: $APT_RC"

# Switch back to CYZX05
echo "[Step 6] Switching back to CYZX05..."
sudo nmcli connection down S50 || true
sleep 2
sudo nmcli connection up CYZX05
sleep 3
ip -4 -br a show wlP2p33s0

# Verify
echo "[Step 7] Verifying..."
which pip3 && pip3 --version
python3 -c "import numpy; print('numpy', numpy.__version__)" 2>&1
python3 -c "import scipy; print('scipy', scipy.__version__)" 2>&1
which cmake && cmake --version | head -1
which tcpdump && echo "tcpdump installed"

echo "=========================================="
echo "=== $(date) RETRY done ==="
echo "=========================================="
