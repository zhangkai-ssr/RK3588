#!/usr/bin/env python3
"""16-channel EMG waveform viewer.

Default offline mode: reads aligned_emg.npz (produced by align_streams.py)
and shows 16 channels in a 4x4 grid using matplotlib.

Live mode (-l/--live): tails the latest emg_*.bin file in the data directory
and updates every 200 ms.

Examples:
  # Offline, full window
  python3 emg_viewer.py --file /tmp/round1_emg.npz

  # Offline, just the first 5 seconds
  python3 emg_viewer.py --file /tmp/round1_emg.npz --window 5

  # Offline, save to PNG without opening a window (for headless host)
  python3 emg_viewer.py --file /tmp/round1_emg.npz --save run1.png --no-show

  # Live from data dir
  python3 emg_viewer.py --live --data-dir /home/orangepi/sensor_host/data

  # Apply 20 Hz HPF + 50 Hz notch (post-firmware-filter)
  python3 emg_viewer.py --file /tmp/round1_emg.npz --filter both
"""
import argparse
import struct
import sys
import time
from pathlib import Path

import numpy as np

try:
    import matplotlib
except ImportError:
    print("matplotlib not installed. On Orange Pi:")
    print("  sudo apt install -y python3-matplotlib")
    sys.exit(1)


# ---------- EMG .bin layout (matches ads1298_stream.c v0x02) ----------
EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
EMG_PKT_LEN = 64
EMG_DEV_LEN = 27
EMG_DEV_COUNT = 2
EMG_CH_PER_DEV = 8
EMG_TOTAL_CH = 16
FRAME_HEADER_SIZE = 8       # host_recv_ns prefix
RECORD_LEN = FRAME_HEADER_SIZE + EMG_PKT_LEN
EMG_SAMPLE_RATE_HZ = 2000


def _int24_be(b: bytes) -> int:
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    if v & 0x800000:
        v -= 0x1000000
    return v


def _shift_left_1bit_27(buf: bytes) -> bytes:
    """ADS1298 daisy-chain dead-bit compensation for chip B's 27 bytes."""
    out = bytearray(27)
    for i in range(26):
        out[i] = ((buf[i] << 1) & 0xFF) | (buf[i + 1] >> 7)
    out[26] = (buf[26] << 1) & 0xFF
    return bytes(out)


# ---------- Loaders ----------
def load_npz(path: Path):
    """Returns (samples [N,16] int32, canonical_ts_ns [N] int64) or (samples, None)."""
    d = np.load(path)
    samples = d["samples"]
    ts = d["canonical_ts_ns"] if "canonical_ts_ns" in d.files else None
    return samples, ts


def load_bin(path: Path, max_samples: int | None = None):
    """Parse raw .bin file (8B host_ts + 64B packet) per record.
    Returns (samples [N,16] int32, host_recv_ns [N] uint64)."""
    data = path.read_bytes()
    n_full = len(data) // RECORD_LEN
    if max_samples is not None:
        n_full = min(n_full, max_samples)
    samples = np.empty((n_full, EMG_TOTAL_CH), dtype=np.int32)
    host_recv = np.empty(n_full, dtype=np.uint64)
    write = 0
    for i in range(n_full):
        off = i * RECORD_LEN
        host_recv[write] = struct.unpack_from("<Q", data, off)[0]
        po = off + FRAME_HEADER_SIZE
        if data[po] != EMG_HDR or data[po + EMG_PKT_LEN - 1] != EMG_FTR:
            continue
        chip_a = bytes(data[po + 9 : po + 9 + EMG_DEV_LEN])
        chip_b = _shift_left_1bit_27(bytes(data[po + 9 + EMG_DEV_LEN : po + 9 + 54]))
        for d_idx, frame in enumerate((chip_a, chip_b)):
            for ch in range(EMG_CH_PER_DEV):
                so = 3 + ch * 3
                samples[write, d_idx * EMG_CH_PER_DEV + ch] = _int24_be(frame[so:so + 3])
        write += 1
    return samples[:write], host_recv[:write]


def find_latest_bin(data_dir: Path) -> Path | None:
    bins = sorted(data_dir.glob("emg_*.bin"), key=lambda p: p.stat().st_mtime)
    return bins[-1] if bins else None


# ---------- Filters (post-firmware) ----------
def apply_filters(samples: np.ndarray, fs: float, mode: str) -> np.ndarray:
    """Apply optional HPF and/or notch to each channel independently."""
    if mode == "raw":
        return samples
    from scipy import signal
    y = samples.astype(np.float64)
    if mode in ("hpf", "both"):
        sos = signal.butter(4, 20.0, btype="highpass", fs=fs, output="sos")
        y = signal.sosfiltfilt(sos, y, axis=0)
    if mode in ("notch", "both"):
        # 50 Hz IIR notch (Q=30)
        b, a = signal.iirnotch(50.0, 30.0, fs=fs)
        y = signal.filtfilt(b, a, y, axis=0)
    return y


# ---------- Plotting ----------
def plot_static(samples: np.ndarray, ts_ns, args):
    import matplotlib.pyplot as plt
    n_samples = len(samples)
    if n_samples < 2:
        print("not enough samples to plot")
        return

    # Time axis in seconds, relative to first sample
    if ts_ns is not None and len(ts_ns) == n_samples:
        t = (ts_ns.astype(np.int64) - int(ts_ns[0])) / 1e9
    else:
        t = np.arange(n_samples) / EMG_SAMPLE_RATE_HZ

    # Window
    start_s = args.start
    end_s = start_s + args.window if args.window > 0 else t[-1]
    sel = (t >= start_s) & (t <= end_s)
    if not sel.any():
        print(f"window [{start_s}s .. {end_s}s] has no samples (total {t[-1]:.2f}s)")
        return
    t_sel = t[sel]
    y = apply_filters(samples[sel], EMG_SAMPLE_RATE_HZ, args.filter)

    fig, axes = plt.subplots(4, 4, figsize=(16, 10), sharex=True,
                             sharey=args.y_shared)
    fig.suptitle(
        f"EMG 16-channel  |  {Path(args.file or args.data_dir).name}  |  "
        f"{t_sel[0]:.2f}s .. {t_sel[-1]:.2f}s  |  filter={args.filter}  |  "
        f"N={len(t_sel)} samples",
        fontsize=11,
    )

    for ch in range(16):
        ax = axes[ch // 4, ch % 4]
        chip = "A" if ch < 8 else "B"
        local = ch % 8 + 1
        color = "tab:blue" if ch < 8 else "tab:orange"
        ax.plot(t_sel, y[:, ch], color=color, linewidth=0.6)
        ax.set_title(f"Chip {chip} ch{local} (idx {ch})", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.3)
        if ch >= 12:
            ax.set_xlabel("time (s)", fontsize=8)
        if ch % 4 == 0:
            ax.set_ylabel("ADC counts", fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.96))

    if args.save:
        fig.savefig(args.save, dpi=120)
        print(f"saved -> {args.save}")
    if not args.no_show:
        plt.show()


def plot_live(args):
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"data dir {data_dir} does not exist")
        return

    fig, axes = plt.subplots(4, 4, figsize=(16, 10), sharex=True,
                             sharey=args.y_shared)
    lines = []
    for ch in range(16):
        ax = axes[ch // 4, ch % 4]
        chip = "A" if ch < 8 else "B"
        local = ch % 8 + 1
        color = "tab:blue" if ch < 8 else "tab:orange"
        (ln,) = ax.plot([], [], color=color, linewidth=0.6)
        ax.set_title(f"Chip {chip} ch{local}", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.3)
        lines.append(ln)

    state = {"current_file": None}
    window_samples = int(args.window * EMG_SAMPLE_RATE_HZ)
    # Each EMG record is 72 bytes; tail roughly 4x window to cover backlog.
    tail_bytes = max(window_samples * RECORD_LEN, 1 << 20)

    def update(_frame):
        latest = find_latest_bin(data_dir)
        if latest is None:
            return lines
        if state["current_file"] != latest:
            print(f"viewing {latest.name}")
            state["current_file"] = latest
        try:
            sz = latest.stat().st_size
            with latest.open("rb") as f:
                f.seek(max(0, sz - tail_bytes))
                buf = f.read()
        except OSError:
            return lines
        # parse only complete records
        n_full = len(buf) // RECORD_LEN
        if n_full < 10:
            return lines
        samples = np.empty((n_full, EMG_TOTAL_CH), dtype=np.int32)
        write = 0
        for i in range(n_full):
            off = i * RECORD_LEN
            po = off + FRAME_HEADER_SIZE
            if buf[po] != EMG_HDR or buf[po + EMG_PKT_LEN - 1] != EMG_FTR:
                continue
            for d_idx in range(EMG_DEV_COUNT):
                base = po + 9 + d_idx * EMG_DEV_LEN
                for ch in range(EMG_CH_PER_DEV):
                    so = base + 3 + ch * 3
                    samples[write, d_idx * EMG_CH_PER_DEV + ch] = _int24_be(buf[so:so + 3])
            write += 1
        if write < 10:
            return lines
        samples = samples[max(0, write - window_samples):write]
        y = apply_filters(samples, EMG_SAMPLE_RATE_HZ, args.filter)
        t = np.arange(len(y)) / EMG_SAMPLE_RATE_HZ
        for ch in range(16):
            lines[ch].set_data(t, y[:, ch])
        for ax in axes.flat:
            ax.relim()
            ax.autoscale_view()
        return lines

    fig.suptitle(f"EMG live (tail {data_dir}) window={args.window}s "
                 f"filter={args.filter}", fontsize=11)
    ani = FuncAnimation(fig, update, interval=int(args.refresh_ms),
                        cache_frame_data=False, blit=False)
    # Keep reference (Matplotlib quirk)
    fig._ani = ani
    plt.show()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="aligned_emg.npz OR raw emg_*.bin path")
    ap.add_argument("--data-dir", default="/home/orangepi/sensor_host/data",
                    help="directory containing emg_*.bin files (live mode)")
    ap.add_argument("--window", type=float, default=5.0,
                    help="time window in seconds (default 5.0)")
    ap.add_argument("--start", type=float, default=0.0,
                    help="window start time in seconds (offline only)")
    ap.add_argument("--filter", choices=("raw", "hpf", "notch", "both"),
                    default="raw",
                    help="optional post-firmware filter (default raw)")
    ap.add_argument("--y-shared", action="store_true",
                    help="share Y axis across all 16 subplots")
    ap.add_argument("--save", help="save figure to PNG and exit (also useful headless)")
    ap.add_argument("--no-show", action="store_true",
                    help="do not open an interactive window (only matters with --save)")
    ap.add_argument("-l", "--live", action="store_true",
                    help="live tail mode")
    ap.add_argument("--refresh-ms", type=float, default=200,
                    help="live update interval in ms (default 200)")
    args = ap.parse_args()

    if args.no_show and not args.save:
        # headless without --save makes no sense; force save
        print("--no-show requires --save; using emg_viewer.png")
        args.save = "emg_viewer.png"

    if args.no_show:
        matplotlib.use("Agg")

    if args.live:
        plot_live(args)
        return

    if not args.file:
        print("ERROR: in offline mode you must pass --file <npz_or_bin>")
        ap.print_usage()
        sys.exit(2)

    p = Path(args.file)
    if not p.exists():
        print(f"file not found: {p}")
        sys.exit(1)

    if p.suffix == ".npz":
        samples, ts = load_npz(p)
        print(f"loaded {len(samples)} samples from {p.name}")
    else:
        samples, host_recv = load_bin(p)
        print(f"loaded {len(samples)} samples from {p.name}")
        ts = host_recv  # use host recv as time axis fallback

    plot_static(samples, ts, args)


if __name__ == "__main__":
    main()
