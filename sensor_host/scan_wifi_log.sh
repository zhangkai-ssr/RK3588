#!/bin/bash
# Record nearby WiFi scan snapshots on Orange Pi.
set -u

OUT="${1:-wifi_scans.log}"
INTERVAL="${2:-60}"
IFACE="${WIFI_IFACE:-}"

scan_once() {
    {
        echo "===== $(date -Is) ====="
        if [ -n "$IFACE" ]; then
            sudo nmcli dev wifi rescan ifname "$IFACE" >/dev/null 2>&1 || true
            nmcli -f IN-USE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL,BARS,SECURITY dev wifi list ifname "$IFACE"
        else
            sudo nmcli dev wifi rescan >/dev/null 2>&1 || true
            nmcli -f IN-USE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL,BARS,SECURITY dev wifi list
        fi
        echo
    } >> "$OUT"
}

if [ "${ONCE:-0}" = "1" ]; then
    scan_once
    exit 0
fi

while true; do
    scan_once
    sleep "$INTERVAL"
done
