# Sensor Host (Orange Pi 5 Plus)

**Orange Pi acts as TCP server**, slave board (with 2x ADS1298 + LSM9DS1TR) connects in over WiFi 2.4G.

## Layout

```
common.py        TCP listen/accept, frame sync, 24-bit BE parse, throughput stats
emg_server.py    EMG: listen :3333, 0xAA/v3/68B @ 2000 SPS, 16 ch x 24-bit
imu_server.py    IMU: listen :3334, 0xBB/v2/215B @ 200 Hz, 9-axis int16
run_all.sh       Run both servers
data/            Raw frames per session (8 B host recv ts ns + N B wire frame)
```

## Slave firmware config

Hardcode the host IP into the slave firmware:

```c
#define HOST_IP   "172.16.212.170"   // Orange Pi current IP
#define EMG_PORT  3333
#define IMU_PORT  3334
```

Slave-side flow: `socket()` -> `connect(HOST_IP, port)` -> stream packets.

## Quick test (no slave hardware needed)

In one shell on Orange Pi:
```bash
cd /home/orangepi/sensor_host && ./run_all.sh
```

In another shell (or from your laptop), pretend to be a slave:
```bash
# Send 5 dummy EMG packets to verify framing works
python3 -c "
import socket, struct, random, time
s = socket.socket(); s.connect(('172.16.212.170', 3333))
for seq in range(5):
    body = b'\\x00\\x00\\x00' + bytes([random.randint(0,255) for _ in range(24)])  # device 1
    body += b'\\x00\\x00\\x00' + bytes([random.randint(0,255) for _ in range(24)]) # device 2
    pkt = bytes([0xAA, 0x03]) + struct.pack('<HQ', seq, time.time_ns()) + bytes([2]) + body + bytes([0x55])
    s.sendall(pkt)
"
```

## Auto-start

```bash
sudo systemctl enable --now sensor-host.service
journalctl -u sensor-host -f
```

## Raw frame file format

```
[8 B host_recv_timestamp_ns LE][N B raw frame]
```

EMG: N = 68. IMU: N = 215. Re-parse offline with `parse_packet()` from the matching server file.

## Protocol assumptions

- Endianness: seq/timestamp little-endian. Pass `--endian big` to EMG if firmware outputs BE.
- IMU layout: 1+1+2+8+1+2(reserved)+200 = 215. If actual firmware uses different padding, adjust `parse_packet()` offsets.
- ADS1298 24-bit samples are big-endian (MSB first) per chip spec; parsed accordingly.
