#!/usr/bin/env python3
"""IMU TCP server (Orange Pi listens, slave board connects in).

Protocol per actual firmware (imu_stream.c):
  Header:     0xBB
  Version:    0x01
  Type:       0x20  (IMU)
  Sequence:   uint16 LE
  Timestamp:  uint32 LE  (esp_timer_get_time(), us since boot of first sample)
  n_samples:  uint8 (= 10)
  Payload:    10 samples x 20 B
                each sample (int16 LE):  ax ay az gx gy gz mx my mz reserved
  Footer:     0x55
  Total:      211 B
Stream rate: 200 Hz sampling, 20 packets/s.
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
    find_header_sync, listen_server, recv_exact, setup_logger,
)
from time_sync import ClockSync

HEADER = 0xBB
FOOTER = 0x55
VERSION = 0x01
PACKET_TYPE = 0x20
PACKET_LEN = 211
SAMPLES_PER_PKT = 10
SAMPLE_LEN = 20

_running = True


def _stop(*_):
    global _running
    _running = False


def parse_packet(buf: bytes):
    if buf[0] != HEADER or buf[1] != VERSION or buf[2] != PACKET_TYPE:
        raise ValueError(
            f"bad header: 0x{buf[0]:02X} ver=0x{buf[1]:02X} type=0x{buf[2]:02X}"
        )
    if buf[-1] != FOOTER:
        raise ValueError(f"bad footer: 0x{buf[-1]:02X}")
    seq, ts_us = struct.unpack_from("<HI", buf, 3)
    n_samples = buf[9]
    if n_samples != SAMPLES_PER_PKT:
        raise ValueError(f"unexpected n_samples={n_samples}")
    # Samples start at offset 10, 10 samples x 20 B each
    samples = np.frombuffer(buf, dtype="<i2", count=SAMPLES_PER_PKT * 10, offset=10)
    samples = samples.reshape(SAMPLES_PER_PKT, 10)
    return seq, ts_us, samples


def handle_one_slave(conn: socket.socket, peer, args, log):
    stats = RateCounter("IMU", log, period=args.stats_period)
    sync = ClockSync("IMU", log, expected_period_us=50_000.0,
                     window=200, report_period_s=args.stats_period,
                     mcu_ts_bits=32)
    fname = ensure_dir(args.outdir) / (
        f"imu_{peer[0].replace('.', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.bin"
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
                seq, ts_us, samples = parse_packet(pkt)
            except ValueError as e:
                log.warning("parse error: %s, resyncing", e)
                find_header_sync(conn, HEADER, log)
                continue
            if out:
                out.write(struct.pack("<Q", host_ts_ns))
                out.write(pkt)
            sync.observe(host_ts_ns, ts_us, seq)
            stats.tick(PACKET_LEN, n_samples=SAMPLES_PER_PKT, seq=seq)
            b = recv_exact(conn, 1)
            if b[0] != HEADER:
                log.warning("post-packet header miss: 0x%02X, resync", b[0])
                find_header_sync(conn, HEADER, log)
    finally:
        if out:
            out.close()
            log.info("closed %s", fname)
        s = sync.summary()
        log.info("IMU session done: pkts=%d unit=%s offset=%.2f ms drift=%+.2f us/s wraps=%d",
                 s.pkts, s.unit, s.offset_ns_mean / 1e6, s.drift_ns_per_sec / 1e3, s.mcu_wraps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=3334)
    ap.add_argument("--outdir", default="/home/orangepi/sensor_host/data")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--stats-period", type=float, default=5.0)
    args = ap.parse_args()

    log = setup_logger("IMU")
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
        log.info("IMU server stopped")


if __name__ == "__main__":
    sys.exit(main())
