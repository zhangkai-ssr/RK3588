#!/usr/bin/env python3
"""IMU TCP client (Orange Pi host side).

Protocol v0x02 (215 B / packet, 20 packets/s, 10 samples per packet => 200 Hz):
  off  size  field
  0    1     header   0xBB
  1    1     version  0x02
  2    2     sequence (uint16)
  4    8     timestamp (uint64)
  12   1     sample_count (= 10)
  13   2     reserved / device_count (assumed 2 B padding for alignment)
  15   200   payload: 10 samples * 20 B each
                 each sample (little-endian int16):
                   ax ay az    gx gy gz    mx my mz    reserved
  214 ?      footer?

Note: total = 1+1+2+8+1+2+200 = 215 (no footer in this layout).
If the slave uses different layout (e.g. 1 B device_count + 200 B payload + 1 B footer = 214),
re-check parse_packet(); the script will log frame errors and re-sync on header.

Slave only starts IMU stream if LSM9DS1TR init OK. If 3334 refuses connections, that's expected.
"""
import argparse
import signal
import socket
import struct
import sys
import time
from pathlib import Path

import numpy as np

from common import (
    RateCounter, connect_with_retry, ensure_dir,
    find_header_sync, recv_exact, setup_logger,
)

HEADER = 0xBB
VERSION = 0x02
PACKET_LEN = 215
SAMPLES_PER_PKT = 10
SAMPLE_LEN = 20  # ax/ay/az gx/gy/gz mx/my/mz reserved => 10 * int16
SAMPLE_RATE_HZ = 200

_running = True


def _stop(*_):
    global _running
    _running = False


def parse_packet(buf: bytes):
    """Parse one IMU packet. Returns (seq, timestamp, samples np.int16[SAMPLES, 10])."""
    if buf[0] != HEADER or buf[1] != VERSION:
        raise ValueError(f"bad header/version: 0x{buf[0]:02X} 0x{buf[1]:02X}")
    seq, ts = struct.unpack_from("<HQ", buf, 2)
    sample_count = buf[12]
    if sample_count != SAMPLES_PER_PKT:
        raise ValueError(f"unexpected sample_count={sample_count}")
    # 13..14 = reserved / device_count (skip)
    samples = np.frombuffer(buf, dtype="<i2", count=SAMPLES_PER_PKT * 10, offset=15)
    samples = samples.reshape(SAMPLES_PER_PKT, 10)  # (10, 10)
    return seq, ts, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="slave (sensor MCU) IP")
    ap.add_argument("--port", type=int, default=3334)
    ap.add_argument("--outdir", default="/home/orangepi/sensor_host/data")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--stats-period", type=float, default=5.0)
    ap.add_argument("--tolerate-missing", action="store_true",
                    help="if slave refuses connection (IMU init failed), just exit cleanly")
    args = ap.parse_args()

    log = setup_logger("IMU")
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    outdir = ensure_dir(args.outdir)
    fname = outdir / f"imu_{time.strftime('%Y%m%d_%H%M%S')}.bin"
    out = None if args.no_record else fname.open("wb")
    if out:
        log.info("recording raw frames -> %s", fname)

    stats = RateCounter("IMU", log, period=args.stats_period)

    try:
        while _running:
            try:
                sock = connect_with_retry(args.host, args.port, log)
                find_header_sync(sock, HEADER, log)
                while _running:
                    rest = recv_exact(sock, PACKET_LEN - 1)
                    pkt = bytes([HEADER]) + rest
                    try:
                        seq, ts, samples = parse_packet(pkt)
                    except ValueError as e:
                        log.warning("parse error: %s, resyncing", e)
                        find_header_sync(sock, HEADER, log)
                        continue
                    if out:
                        host_ts_ns = time.time_ns()
                        out.write(struct.pack("<Q", host_ts_ns))
                        out.write(pkt)
                    stats.tick(PACKET_LEN, n_samples=SAMPLES_PER_PKT, seq=seq)
                    b = recv_exact(sock, 1)
                    if b[0] != HEADER:
                        log.warning("post-packet header miss: 0x%02X, resync", b[0])
                        find_header_sync(sock, HEADER, log)
            except ConnectionRefusedError:
                if args.tolerate_missing:
                    log.warning("slave refused 3334 (LSM9DS1TR init likely failed); exiting")
                    return 0
                log.error("connection refused, retry in 5s")
                time.sleep(5)
            except (ConnectionError, OSError, socket.error) as e:
                log.error("stream error: %s, reconnect in 2s", e)
                time.sleep(2)
    finally:
        if out:
            out.close()
            log.info("closed %s", fname)
        log.info("IMU client stopped")


if __name__ == "__main__":
    sys.exit(main())
