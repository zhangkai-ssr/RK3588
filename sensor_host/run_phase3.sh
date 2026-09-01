#!/bin/bash
# Phase 3: 3 rounds x 60s stability test.
# For each round: clean data dir, restart sensor-host (forces slave reconnect),
# wait 70 s, run align_streams, save report.
set -u

REPORT_DIR=/tmp/phase3_reports
mkdir -p "$REPORT_DIR"

for r in 1 2 3; do
    echo "================================================================"
    echo " Round $r — clearing data and restarting sensor-host"
    echo "================================================================"
    rm -f /home/orangepi/sensor_host/data/*.bin
    sudo systemctl restart sensor-host
    sleep 3
    echo "Recording for 65 seconds..."
    sleep 65
    echo "Done recording. Running align_streams..."
    cd /home/orangepi/sensor_host && \
        python3 align_streams.py --data-dir data \
            --out-prefix "$REPORT_DIR/round${r}" 2>&1 | tail -25
    echo
done

echo "================================================================"
echo " ALL 3 ROUNDS COMPLETE — comparing"
echo "================================================================"
for r in 1 2 3; do
    echo "--- Round $r ---"
    grep -E "packets:|duration:|avg rate:|slope=|residual_std=|passed=|sequence gaps:|p99=" \
        "$REPORT_DIR/round${r}_report.txt" 2>/dev/null
    echo
done
