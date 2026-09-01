#!/bin/bash
LOG=/tmp/install_via_hotspot.log
exec > >(tee -a "$LOG") 2>&1
echo
echo "=========================================="
echo "=== $(date) Hotspot install start ==="
echo "=========================================="

HOTSPOT_SSID="S50"
HOTSPOT_PASS="12345678qwe"
HOME_SSID="CYZX05"

# Step 1: Create S50 connection if not exists
if ! sudo nmcli connection show "$HOTSPOT_SSID" >/dev/null 2>&1; then
    echo "[Step 1] Creating $HOTSPOT_SSID connection..."
    sudo nmcli connection add type wifi con-name "$HOTSPOT_SSID" \
        ifname wlP2p33s0 ssid "$HOTSPOT_SSID"
    sudo nmcli connection modify "$HOTSPOT_SSID" \
        802-11-wireless-security.key-mgmt wpa-psk \
        802-11-wireless-security.psk "$HOTSPOT_PASS" \
        802-11-wireless.band bg \
        ipv4.method auto \
        connection.autoconnect no
else
    echo "[Step 1] $HOTSPOT_SSID connection already exists"
fi

# Step 2: Switch from CYZX05 to S50
echo "[Step 2] Switching from $HOME_SSID to $HOTSPOT_SSID..."
sudo nmcli connection down "$HOME_SSID" 2>&1 || true
sleep 2
sudo nmcli connection up "$HOTSPOT_SSID"
SWITCH_RC=$?
if [ $SWITCH_RC -ne 0 ]; then
    echo "[ERROR] Failed to connect $HOTSPOT_SSID (rc=$SWITCH_RC). Rolling back."
    sudo nmcli connection up "$HOME_SSID" || true
    exit 1
fi
sleep 3

# Step 3: Verify internet
echo "[Step 3] Verifying internet..."
ip -4 -br a show wlP2p33s0
OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sI -m 5 http://repo.huaweicloud.com/ubuntu-ports/ 2>&1 | head -1 | grep -qE "200|301"; then
        echo "Internet check passed on try $i"
        OK=1
        break
    fi
    echo "Try $i: not yet, sleeping 3s"
    sleep 3
done

if [ $OK -ne 1 ]; then
    echo "[ERROR] No internet after 30s. Switching back to $HOME_SSID."
    sudo nmcli connection down "$HOTSPOT_SSID" || true
    sudo nmcli connection up "$HOME_SSID" || true
    exit 1
fi

# Step 4: apt update + install
echo "[Step 4] apt update..."
sudo apt-get update -y 2>&1 | tail -20
echo
echo "[Step 4b] apt install python3-pip python3-numpy python3-scipy cmake tcpdump..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3-pip python3-numpy python3-scipy cmake tcpdump 2>&1 | tail -30
APT_RC=${PIPESTATUS[0]}
echo "[Step 4] apt install exit code: $APT_RC"

# Step 5: Switch back to CYZX05
echo "[Step 5] Switching back to $HOME_SSID..."
sudo nmcli connection down "$HOTSPOT_SSID" || true
sleep 2
sudo nmcli connection up "$HOME_SSID"
sleep 3
ip -4 -br a show wlP2p33s0

# Step 6: Verify installs
echo "[Step 6] Verifying installs..."
which pip3 && pip3 --version
python3 -c "import numpy; print('numpy', numpy.__version__)" 2>&1
python3 -c "import scipy; print('scipy', scipy.__version__)" 2>&1
which cmake && cmake --version | head -1
which tcpdump && echo "tcpdump OK"

echo "=========================================="
echo "=== $(date) All done ==="
echo "=========================================="
