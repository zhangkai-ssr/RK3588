#!/usr/bin/env python3
"""EMG TCP server (Orange Pi listens, slave board connects in).

Protocol per actual firmware (ads1298_stream.c):
  Header:    0xAA
  Version:   0x02
  Sequence:  uint16 LE
  Timestamp: uint32 LE  (esp_timer_get_time(), us since boot, wraps at ~71 min)
  device_ct: uint8  (= 2)
  Payload:   54 B  (2 devices x 27 B: 3 B status + 8 ch x 3 B BE 24-bit signed)
  Footer:    0x55
  Total:     64 B
Stream rate: 2000 SPS, batched 50 packets per send by firmware.
"""
import argparse
import signal
import socket
import struct
import sys
import time

import numpy as np

from common import (
    RateCounter, accept_slave, ensure_dir,
    find_header_sync, listen_server, parse_int24_be, recv_exact, setup_logger,
)
from time_sync import ClockSync

HEADER = 0xAA
FOOTER = 0x55
VERSION = 0x02
PACKET_LEN = 64
DEVICE_LEN = 27
CHANNELS_PER_DEVICE = 8
DEVICE_COUNT = 2
TOTAL_CHANNELS = CHANNELS_PER_DEVICE * DEVICE_COUNT  # 16

_running = True


def _stop(*_):
    global _running
    _running = False


def parse_packet(buf: bytes):
    """Parse one 64 B EMG packet. Returns (seq, ts_us, statuses[2], samples_16ch_int32)."""
    if buf[0] != HEADER or buf[-1] != FOOTER or buf[1] != VERSION:
        raise ValueError(
            f"bad framing: hdr=0x{buf[0]:02X} ver=0x{buf[1]:02X} ftr=0x{buf[-1]:02X}"
        )
    seq, ts_us = struct.unpack_from("<HI", buf, 2)
    dev_count = buf[8]
    if dev_count != DEVICE_COUNT:
        raise ValueError(f"unexpected device_count={dev_count}")
    statuses = []
    samples = np.empty(TOTAL_CHANNELS, dtype=np.int32)
    for d in range(DEVICE_COUNT):
        base = 9 + d * DEVICE_LEN
        statuses.append(int.from_bytes(buf[base:base + 3], "big"))
        for ch in range(CHANNELS_PER_DEVICE):
            off = base + 3 + ch * 3
            samples[d * CHANNELS_PER_DEVICE + ch] = parse_int24_be(buf[off:off + 3])
    return seq, ts_us, statuses, samples


def handle_one_slave(conn: socket.socket, peer, args, log):
    stats = RateCounter("EMG", log, period=args.stats_period)
    # ADS1298 actual rate ~2724 SPS (see project notes on fCLK). EMG firmware
    # sends 50-frame batches, so p99 inter-arrival ~= batch period ~20ms.
    sync = ClockSync("EMG", log, expected_period_us=367.0,
                     window=4000, report_period_s=args.stats_period,
                     mcu_ts_bits=32, batch_threshold_ms=30.0)
    fname = ensure_dir(args.outdir) / (
        f"emg_{peer[0].replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.bin"
    )
    out = None if args.no_record else fname.open("wb")
    if out:
        log.info("recording raw frames -> %s", fname)
    try:
        find_header_sync(conn, HEADER, log)
        while _running:
            rest = recv_exact(conn, PACKET_LEN - 1)
            host_ts_ns = time.time_ns()
            pkt = bytes([HEADER]) + rest
            try:
                seq, ts_us, statuses, samples = parse_packet(pkt)
            except ValueError as e:
                log.warning("parse error: %s, resyncing", e)
                find_header_sync(conn, HEADER, log)
                continue
            if out:
                out.write(struct.pack("<Q", host_ts_ns))
                out.write(pkt)
            sync.observe(host_ts_ns, ts_us, seq)
            stats.tick(PACKET_LEN, n_samples=1, seq=seq)
            b = recv_exact(conn, 1)
            if b[0] != HEADER:
                log.warning("post-packet header miss: 0x%02X, resync", b[0])
                find_header_sync(conn, HEADER, log)
    finally:
        if out:
            out.close()
            log.info("closed %s", fname)
        s = sync.summary()
        log.info("EMG session done: pkts=%d unit=%s offset=%.2f ms drift=%+.2f us/s wraps=%d",
                 s.pkts, s.unit, s.offset_ns_mean / 1e6, s.drift_ns_per_sec / 1e3, s.mcu_wraps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=3333)
    ap.add_argument("--outdir", default="/home/orangepi/sensor_host/data")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--stats-period", type=float, default=5.0)
    args = ap.parse_args()

    log = setup_logger("EMG")
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    srv = listen_server(args.bind, args.port, log)
    try:
        while _running:
            try:
                accepted = accept_slave(srv, log)
            except OSError as e:
                log.error("accept failed: %s", e)
                time.sleep(1)
                continue
            if accepted is None:
                continue
            conn, peer = accepted
            try:
                handle_one_slave(conn, peer, args, log)
            except (ConnectionError, OSError) as e:
                log.warning("slave %s session ended: %s", peer[0], e)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                log.info("ready for next slave connection on :%d", args.port)
    finally:
        srv.close()
        log.info("EMG server stopped")


if __name__ == "__main__":
    sys.exit(main())
