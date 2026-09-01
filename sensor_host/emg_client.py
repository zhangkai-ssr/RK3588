#!/usr/bin/env python3
"""EMG TCP client (Orange Pi host side).

Protocol v0x03 (68 B / packet, 2000 SPS, 16-ch ADS1298 x2):
  off  size  field
  0    1     header   0xAA
  1    1     version  0x03
  2    2     sequence (uint16)
  4    8     timestamp (uint64)
  12   1     device_count (= 2)
  13   27    device #1: 3 B status + 8 ch * 3 B (24-bit BE signed)
  40   27    device #2: 3 B status + 8 ch * 3 B
  67   1     footer   0x55
Total: 68 B. Endianness of seq/ts is little-endian by ARM convention; flip with --big-endian if needed.
"""
import argparse
import signal
import struct
import sys
import time
from pathlib import Path

import numpy as np

from common import (
    RateCounter, connect_with_retry, ensure_dir,
    find_header_sync, parse_int24_be, recv_exact, setup_logger,
)

HEADER = 0xAA
FOOTER = 0x55
VERSION = 0x03
PACKET_LEN = 68
DEVICE_LEN = 27
CHANNELS_PER_DEVICE = 8
DEVICE_COUNT = 2
TOTAL_CHANNELS = CHANNELS_PER_DEVICE * DEVICE_COUNT  # 16
SAMPLE_RATE = 2000

_running = True


def _stop(*_):
    global _running
    _running = False


def parse_packet(buf: bytes, endian: str):
    """Parse one 68 B EMG packet. Returns (seq, timestamp, status[2], samples_16ch_int32)."""
    if buf[0] != HEADER or buf[-1] != FOOTER or buf[1] != VERSION:
        raise ValueError(
            f"bad framing: hdr=0x{buf[0]:02X} ver=0x{buf[1]:02X} ftr=0x{buf[-1]:02X}"
        )
    fmt = "<HQ" if endian == "little" else ">HQ"
    seq, ts = struct.unpack_from(fmt, buf, 2)
    dev_count = buf[12]
    if dev_count != DEVICE_COUNT:
        raise ValueError(f"unexpected device_count={dev_count}")

    statuses = []
    samples = np.empty(TOTAL_CHANNELS, dtype=np.int32)
    for d in range(DEVICE_COUNT):
        base = 13 + d * DEVICE_LEN
        statuses.append(int.from_bytes(buf[base:base + 3], "big"))
        for ch in range(CHANNELS_PER_DEVICE):
            off = base + 3 + ch * 3
            samples[d * CHANNELS_PER_DEVICE + ch] = parse_int24_be(buf[off:off + 3])
    return seq, ts, statuses, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="slave (sensor MCU) IP")
    ap.add_argument("--port", type=int, default=3333)
    ap.add_argument("--endian", choices=("little", "big"), default="little",
                    help="byte order for seq/ts (default little)")
    ap.add_argument("--outdir", default="/home/orangepi/sensor_host/data",
                    help="where to dump captured frames")
    ap.add_argument("--no-record", action="store_true",
                    help="skip writing to disk (just count throughput)")
    ap.add_argument("--stats-period", type=float, default=5.0)
    args = ap.parse_args()

    log = setup_logger("EMG")
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    outdir = ensure_dir(args.outdir)
    fname = outdir / f"emg_{time.strftime('%Y%m%d_%H%M%S')}.bin"
    out = None if args.no_record else fname.open("wb")
    if out:
        log.info("recording raw frames -> %s", fname)

    stats = RateCounter("EMG", log, period=args.stats_period)

    try:
        while _running:
            try:
                sock = connect_with_retry(args.host, args.port, log)
                # Initial sync
                find_header_sync(sock, HEADER, log)
                # We've already consumed the header byte; read the rest 67 B
                while _running:
                    rest = recv_exact(sock, PACKET_LEN - 1)
                    pkt = bytes([HEADER]) + rest
                    try:
                        seq, ts, statuses, samples = parse_packet(pkt, args.endian)
                    except ValueError as e:
                        log.warning("parse error: %s, resyncing", e)
                        find_header_sync(sock, HEADER, log)
                        continue
                    if out:
                        # store with a host-side recv timestamp to ease later alignment
                        host_ts_ns = time.time_ns()
                        out.write(struct.pack("<Q", host_ts_ns))
                        out.write(pkt)
                    stats.tick(PACKET_LEN, n_samples=1, seq=seq)
                    # Read header byte of the next packet, expect 0xAA
                    b = recv_exact(sock, 1)
                    if b[0] != HEADER:
                        log.warning("post-packet header miss: 0x%02X, resync", b[0])
                        find_header_sync(sock, HEADER, log)
            except (ConnectionError, OSError, socket.error) as e:  # noqa: F821
                log.error("stream error: %s, reconnect in 2s", e)
                time.sleep(2)
    finally:
        if out:
            out.close()
            log.info("closed %s", fname)
        log.info("EMG client stopped")


if __name__ == "__main__":
    import socket  # for the OSError in main()
    sys.exit(main())
