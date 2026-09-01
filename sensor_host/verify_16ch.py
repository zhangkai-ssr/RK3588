#!/usr/bin/env python3
"""Verify 16-channel EMG daisy-chain integrity from a recorded .npz file."""
import sys
import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/finalrun_emg.npz"
d = np.load(path)
print(f"file: {path}")
print(f"packets: {len(d['samples'])}")
print(f"samples shape: {d['samples'].shape}")
print(f"status shape: {d['status'].shape}")
print()

print("=== STATUS BYTES (first 5 packets, 2 chips each) ===")
for i in range(5):
    sa = int(d["status"][i, 0])
    sb = int(d["status"][i, 1])
    print(f"  pkt {i}: chip-A=0x{sa:06X}  chip-B=0x{sb:06X}")
print()

print("=== Per-channel stats (entire window) ===")
print("(chip A = ch0..7, chip B = ch8..15)")
print(f"{'ch':>3} {'chip':>4} {'mean':>13} {'std':>10} {'p1':>11} {'p99':>11} {'zeros':>7}")
print("-" * 70)
samples = d["samples"]
for ch in range(16):
    chip = "A" if ch < 8 else "B"
    local_ch = ch % 8 + 1
    s = samples[:, ch]
    mean = s.mean()
    std = s.std()
    p1 = np.percentile(s, 1)
    p99 = np.percentile(s, 99)
    n_zero = int(np.sum(s == 0))
    flag = " ❌ DEAD" if std < 10 else (" ⚠ flat" if std < 1000 else "")
    print(f"{ch:3d} {chip}/{local_ch:<2d} {mean:+13.0f} {std:10.0f} "
          f"{p1:+11.0f} {p99:+11.0f} {n_zero:7d}{flag}")

print()
print("=== Inter-chip correlation (chain integrity sanity) ===")
# If both chips share the same RLD reference and PCB ground noise,
# they should be weakly correlated even with shorted inputs.
chA = samples[:, :8].astype(np.float64)
chB = samples[:, 8:].astype(np.float64)
mean_chA = chA.mean(axis=1)
mean_chB = chB.mean(axis=1)
if mean_chA.std() > 0 and mean_chB.std() > 0:
    corr = np.corrcoef(mean_chA, mean_chB)[0, 1]
    print(f"corr(mean_chipA, mean_chipB) = {corr:+.4f}")
else:
    print("one chip is fully dead - no correlation")
