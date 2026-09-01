#!/usr/bin/env python3
"""Pretend to be the actual slave firmware and send EMG/IMU packets at real rates.

Protocol matches ads1298_stream.c / imu_stream.c:
  EMG  64 B  ver=0x02, ts=uint32 us since (fake) boot
  IMU  211 B ver=0x01 type=0x20, ts=uint32 us since (fake) boot
"""
import argparse
import socket
import struct
import time

EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
IMU_HDR, IMU_VER, IMU_TYPE, IMU_FTR = 0xBB, 0x01, 0x20, 0x55

T_BOOT_NS = time.time_ns()


def mcu_now_us() -> int:
    return ((time.time_ns() - T_BOOT_NS) // 1000) & 0xFFFFFFFF


def make_emg(seq: int) -> bytes:
    body = bytearray()
    for dev in range(2):
        body += bytes([0xC0, 0x00, 0x00])
        for ch in range(8):
            val = ((dev * 8 + ch) * 100 + seq) & 0xFFFFFF
            body += bytes([(val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF])
    pkt = bytes([EMG_HDR, EMG_VER])
    pkt += struct.pack("<HI", seq & 0xFFFF, mcu_now_us())
    pkt += bytes([2]) + bytes(body) + bytes([EMG_FTR])
    assert len(pkt) == 64, len(pkt)
    return pkt


def make_imu(seq: int) -> bytes:
    pkt = bytearray([IMU_HDR, IMU_VER, IMU_TYPE])
    pkt += struct.pack("<HI", seq & 0xFFFF, mcu_now_us())
    pkt += bytes([10])
    for s in range(10):
        vals = [(seq + s * 10 + i) & 0xFFFF for i in range(9)] + [0]
        pkt += struct.pack("<10h", *[v if v < 0x8000 else v - 0x10000 for v in vals])
    pkt += bytes([IMU_FTR])
    assert len(pkt) == 211, len(pkt)
    return bytes(pkt)


def stream(host: str, port: int, builder, rate_hz: float, n: int, label: str):
    s = socket.socket()
    s.connect((host, port))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print(f"[{label}] connected to {host}:{port}")
    period = 1.0 / rate_hz
    t_next = time.monotonic()
    for seq in range(n):
        s.sendall(builder(seq))
        t_next += period
        sleep = t_next - time.monotonic()
        if sleep > 0:
            time.sleep(sleep)
    s.close()
    print(f"[{label}] sent {n} packets")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--only", choices=("emg", "imu", "both"), default="both")
    args = ap.parse_args()

    if args.only in ("emg", "both"):
        n = int(2000 * args.seconds)
        stream(args.host, 3333, make_emg, 2000.0, n, "EMG")
    if args.only in ("imu", "both"):
        n = int(20 * args.seconds)
        stream(args.host, 3334, make_imu, 20.0, n, "IMU")


if __name__ == "__main__":
    main()
