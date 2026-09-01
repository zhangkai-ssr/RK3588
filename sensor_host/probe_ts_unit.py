#!/usr/bin/env python3
"""Sniff a few packets and print the raw 8-byte timestamp field to figure out unit.

Reads from a port (3333 EMG or 3334 IMU) by accepting one slave connection,
grabs ~10 packets, prints timestamp values + magnitude analysis, then quits.
The running sensor-host.service will pick up next reconnect automatically.
"""
import argparse
import socket
import struct
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3333)
    ap.add_argument("--samples", type=int, default=10)
    args = ap.parse_args()

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"listening :{args.port}, waiting for slave...")
    conn, peer = srv.accept()
    print(f"slave connected from {peer}")

    # find first 0xAA (EMG) or 0xBB (IMU)
    target_header = 0xAA if args.port == 3333 else 0xBB
    packet_len = 68 if args.port == 3333 else 215

    # resync to header
    while True:
        b = conn.recv(1)
        if b and b[0] == target_header:
            break

    host_ns_list = []
    slave_ts_list = []

    for i in range(args.samples):
        buf = bytearray([target_header])
        while len(buf) < packet_len:
            chunk = conn.recv(packet_len - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        host_ns = time.time_ns()
        if len(buf) < packet_len:
            print("short read, exiting")
            break
        ver = buf[1]
        seq = struct.unpack_from("<H", buf, 2)[0]
        slave_ts = struct.unpack_from("<Q", buf, 4)[0]
        host_ns_list.append(host_ns)
        slave_ts_list.append(slave_ts)
        print(f"#{i:2d} ver=0x{ver:02X} seq={seq:5d} slave_ts={slave_ts:>20d} "
              f"host_ns={host_ns}")

    conn.close()
    srv.close()

    if not slave_ts_list:
        print("no packets received")
        return 1

    print()
    print("=== analysis ===")
    avg_slave = sum(slave_ts_list) // len(slave_ts_list)
    print(f"avg slave_ts magnitude: {avg_slave:.3e}")

    candidates = {
        "epoch_seconds":     1.7e9,
        "epoch_ms":          1.7e12,
        "epoch_us":          1.7e15,
        "epoch_ns":          1.7e18,
        "tick_us (5 days)":  4e11,  # rough heuristic
        "tick_ms (5 days)":  4e8,
    }
    for name, ref in candidates.items():
        ratio = avg_slave / ref
        if 0.1 <= ratio <= 10:
            print(f"  candidate: {name} (ratio {ratio:.2f})")

    # inter-packet delta
    if len(slave_ts_list) >= 2:
        deltas = [slave_ts_list[i + 1] - slave_ts_list[i]
                  for i in range(len(slave_ts_list) - 1)]
        avg_delta = sum(deltas) / len(deltas)
        print(f"avg inter-packet slave_ts delta: {avg_delta}")
        # for EMG 2000 SPS, expect delta ~500 us = 0.5 ms = 0.0005 s
        # for IMU 20 pkt/s, expect delta ~50 ms = 50000 us
        if args.port == 3333:
            print("  EMG expects: 500 if us, 0.5 if ms, 500000 if ns")
        else:
            print("  IMU expects: 50000 if us, 50 if ms, 5e7 if ns")

    # offset host - slave
    if avg_slave > 1e9:  # looks like wall-clock
        # try assuming us first
        host_us = host_ns_list[-1] // 1000
        host_ms = host_ns_list[-1] // 1_000_000
        print(f"host_ns={host_ns_list[-1]} host_us={host_us} host_ms={host_ms}")
        print(f"slave_ts last={slave_ts_list[-1]}")
        for unit, scale in [("ns", 1), ("us", 1000), ("ms", 1_000_000)]:
            slave_ns = slave_ts_list[-1] * scale
            diff_ms = (host_ns_list[-1] - slave_ns) / 1e6
            print(f"  if slave is {unit}: offset = {diff_ms:+.3f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
