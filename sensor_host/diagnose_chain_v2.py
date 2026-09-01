#!/usr/bin/env python3
"""Daisy-chain analysis with 'dead bit' shift compensation.

Theory: ADS1298 daisy chain inserts 1 'don't care' bit between each chip's
216-bit data. Our SPI reads 54 bytes (432 bits) straight through without
accounting for that dead bit, so chip B's data is right-shifted by 1 bit.

Compensation: shift chip B's 27 bytes LEFT by 1 bit, borrowing from the
following byte. Then re-check status validity.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np

EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
EMG_PKT_LEN = 64
FRAME_HDR = 8


def _int24_be(b: bytes) -> int:
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    if v & 0x800000:
        v -= 0x1000000
    return v


def shift_left_1bit(buf: bytes) -> bytes:
    """Left-shift the entire byte stream by 1 bit (MSB-first).
    The last byte's LSB is lost (no data to pull from)."""
    out = bytearray(len(buf))
    for i in range(len(buf) - 1):
        out[i] = ((buf[i] << 1) & 0xFF) | (buf[i + 1] >> 7)
    out[-1] = (buf[-1] << 1) & 0xFF
    return bytes(out)


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/finalrun.bin")
    data = path.read_bytes()
    record_len = FRAME_HDR + EMG_PKT_LEN
    n = len(data) // record_len
    print(f"file: {path}  records: {n}")

    n_a_valid = 0
    n_b_valid_raw = 0
    n_b_valid_shift = 0
    a_first = Counter()
    b_first_raw = Counter()
    b_first_shift = Counter()
    chB_samples_raw = []
    chB_samples_shift = []

    for i in range(n):
        off = i * record_len
        pkt_off = off + FRAME_HDR
        if data[pkt_off] != EMG_HDR or data[pkt_off + EMG_PKT_LEN - 1] != EMG_FTR:
            continue
        payload = data[pkt_off + 9 : pkt_off + 9 + 54]
        a_status = payload[0:3]
        b_raw = payload[27:54]              # chip B 27 bytes, raw
        b_shift = shift_left_1bit(b_raw)    # chip B 27 bytes, shifted left 1 bit
        b_status_raw = b_raw[0:3]
        b_status_shift = b_shift[0:3]

        if (a_status[0] & 0xF0) == 0xC0:
            n_a_valid += 1
        if (b_status_raw[0] & 0xF0) == 0xC0:
            n_b_valid_raw += 1
        if (b_status_shift[0] & 0xF0) == 0xC0:
            n_b_valid_shift += 1

        a_first[a_status[0]] += 1
        b_first_raw[b_status_raw[0]] += 1
        b_first_shift[b_status_shift[0]] += 1

        # collect a few ch1 values to inspect
        if 100 < i < 200:
            chB_samples_raw.append(_int24_be(b_raw[3:6]))
            chB_samples_shift.append(_int24_be(b_shift[3:6]))

    print()
    print("=" * 70)
    print(" STATUS BYTE VALIDITY (high 4 bits == 1100)")
    print("=" * 70)
    print(f"  chip A             valid:   {n_a_valid:>7} / {n}  ({n_a_valid*100/n:.2f}%)")
    print(f"  chip B raw bytes:           {n_b_valid_raw:>7} / {n}  ({n_b_valid_raw*100/n:.2f}%)")
    print(f"  chip B shift-left-1-bit:    {n_b_valid_shift:>7} / {n}  ({n_b_valid_shift*100/n:.2f}%)  ★")

    print()
    print("=" * 70)
    print(" Chip B status byte 0 — TOP 5 values (RAW vs SHIFTED)")
    print("=" * 70)
    print("  RAW:")
    for byte, cnt in b_first_raw.most_common(5):
        print(f"    0x{byte:02X}  count={cnt:>7}  ({cnt*100/n:.2f}%)")
    print("  SHIFTED LEFT 1 BIT:")
    for byte, cnt in b_first_shift.most_common(5):
        valid = "  ✓" if (byte & 0xF0) == 0xC0 else ""
        print(f"    0x{byte:02X}  count={cnt:>7}  ({cnt*100/n:.2f}%) {valid}")

    print()
    print("=" * 70)
    print(" Chip B channel-1 sample value (idx 100..200)")
    print("=" * 70)
    if chB_samples_shift:
        import statistics
        print(f"  raw mean:    {statistics.mean(chB_samples_raw):+.0f}  "
              f"stdev: {statistics.stdev(chB_samples_raw):.0f}")
        print(f"  shift mean:  {statistics.mean(chB_samples_shift):+.0f}  "
              f"stdev: {statistics.stdev(chB_samples_shift):.0f}")

    print()
    if n_b_valid_shift > 0.95 * n:
        print("✅ DEAD-BIT THEORY CONFIRMED — fix is to shift chip B data left by 1 bit.")
        print("   firmware-side fix: read 55 bytes instead of 54, drop bit 216 (the dead bit).")
    else:
        print("⚠️  shifting by 1 bit didn't restore chip B status validity. Try other offsets?")


if __name__ == "__main__":
    sys.exit(main())
