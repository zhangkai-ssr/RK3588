#!/usr/bin/env python3
"""Daisy-chain integrity diagnosis from an EMG .bin file.

For each packet:
- Verify ADS1298 status byte high 4 bits == 1100 (0xC) for chip A AND chip B
- Bin status byte values and find dominant patterns
- Count packets where chip B drove its DOUT at all (vs. floating)
- Sample raw 54B payloads to dump in hex

This is a passive analysis — no firmware change needed.

Usage:
  python3 diagnose_chain.py /path/to/emg_xxx.bin
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


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/finalrun.bin")
    data = path.read_bytes()
    record_len = FRAME_HDR + EMG_PKT_LEN
    n = len(data) // record_len
    print(f"file: {path}  records: {n}")

    if n == 0:
        return 1

    # Aggregate
    n_a_valid = 0      # chip A status byte high 4 bits == 1100
    n_b_valid = 0      # chip B status byte high 4 bits == 1100
    n_b_zero = 0       # chip B status all zero (floating low)
    n_b_allone = 0     # chip B status all 0xFF (floating high)
    n_a_zero = 0
    a_status0 = Counter()
    b_status0 = Counter()
    a_first_byte = Counter()
    b_first_byte = Counter()

    samples = []

    for i in range(n):
        off = i * record_len
        pkt_off = off + FRAME_HDR
        # header check
        if data[pkt_off] != EMG_HDR or data[pkt_off + EMG_PKT_LEN - 1] != EMG_FTR:
            continue

        # Payload starts at pkt_off + 9, 54 bytes total
        payload = data[pkt_off + 9 : pkt_off + 9 + 54]
        a_status = payload[0:3]
        b_status = payload[27:30]

        a0 = a_status[0]
        b0 = b_status[0]
        a_first_byte[a0] += 1
        b_first_byte[b0] += 1
        a_status0[bytes(a_status)] += 1
        b_status0[bytes(b_status)] += 1

        if (a0 & 0xF0) == 0xC0:
            n_a_valid += 1
        if (b0 & 0xF0) == 0xC0:
            n_b_valid += 1
        if a_status == b"\x00\x00\x00":
            n_a_zero += 1
        if b_status == b"\x00\x00\x00":
            n_b_zero += 1
        if b_status == b"\xff\xff\xff":
            n_b_allone += 1

        if i < 5:
            samples.append((i, payload))

    print()
    print("=" * 70)
    print(" STATUS BYTE VALIDITY")
    print("=" * 70)
    print(f"  packets analyzed: {n}")
    print(f"  chip A status valid (byte0 high4 = 1100): "
          f"{n_a_valid:>6} / {n}  ({n_a_valid*100/n:.2f}%)")
    print(f"  chip B status valid (byte0 high4 = 1100): "
          f"{n_b_valid:>6} / {n}  ({n_b_valid*100/n:.2f}%)")
    print(f"  chip A status all zero:  {n_a_zero:>6} ({n_a_zero*100/n:.2f}%)")
    print(f"  chip B status all zero:  {n_b_zero:>6} ({n_b_zero*100/n:.2f}%)")
    print(f"  chip B status all 0xFF:  {n_b_allone:>6} ({n_b_allone*100/n:.2f}%)")

    print()
    print("=" * 70)
    print(" TOP-10 chip A status byte 0 values")
    print("=" * 70)
    for byte, cnt in a_first_byte.most_common(10):
        valid = "✓ valid" if (byte & 0xF0) == 0xC0 else "  -"
        print(f"  0x{byte:02X}  count={cnt:>6}  ({cnt*100/n:5.2f}%)  {valid}")

    print()
    print("=" * 70)
    print(" TOP-10 chip B status byte 0 values")
    print("=" * 70)
    for byte, cnt in b_first_byte.most_common(10):
        valid = "✓ valid" if (byte & 0xF0) == 0xC0 else "  -"
        print(f"  0x{byte:02X}  count={cnt:>6}  ({cnt*100/n:5.2f}%)  {valid}")

    print()
    print("=" * 70)
    print(" FIRST 5 PACKETS RAW PAYLOAD (54 B = 27 chip A + 27 chip B)")
    print("=" * 70)
    for idx, payload in samples:
        print(f"  pkt {idx}:")
        a_hex = payload[0:27].hex()
        b_hex = payload[27:54].hex()
        print(f"    chip A: {a_hex}")
        print(f"    chip B: {b_hex}")

    print()
    print("=" * 70)
    print(" VERDICT")
    print("=" * 70)
    if n_a_valid > 0.99 * n:
        print("  ✅ chip A daisy chain output is CLEAN — chip A is healthy.")
    elif n_a_valid > 0.5 * n:
        print(f"  ⚠️  chip A status valid only {n_a_valid*100/n:.1f}% of time — "
              "SPI byte alignment / chain bit-slippage issue?")
    else:
        print(f"  ❌ chip A status valid only {n_a_valid*100/n:.1f}% — "
              "chip A has SPI/configuration problem.")

    if n_b_valid < 0.01 * n:
        print(f"  ❌ chip B status valid only {n_b_valid*100/n:.2f}% — "
              "chip B is NOT driving DOUT in daisy chain.")
        print("     Hardware to check: chip B's CLK pin, CLKSEL pin, AVDD, RESET.")
    elif n_b_valid > 0.99 * n:
        print(f"  ✅ chip B status valid {n_b_valid*100/n:.1f}% — chip B working OK.")
    else:
        print(f"  ⚠️  chip B status valid {n_b_valid*100/n:.1f}% — intermittent.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
