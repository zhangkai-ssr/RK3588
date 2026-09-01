#!/bin/bash
# Launch EMG + IMU TCP servers (Orange Pi listens, slave connects in).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

python3 emg_server.py --port 3333 &
EMG_PID=$!
echo "EMG server pid=$EMG_PID listen :3333"

python3 imu_server.py --port 3334 &
IMU_PID=$!
echo "IMU server pid=$IMU_PID listen :3334"

trap 'echo "stopping..."; kill -TERM $EMG_PID $IMU_PID 2>/dev/null; wait' INT TERM
wait
