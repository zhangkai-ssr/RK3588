#!/usr/bin/env python3
"""Real-time 16-channel EMG viewer for Windows.

Streams the most recent emg_*.bin on the Orange Pi via SSH (`tail -c 0 -f`),
decodes the 16 channels live, and renders a rolling-window plot in a 4x4
matplotlib grid. Refreshes every 200 ms by default.

Usage:
    python emg_live_win.py
    python emg_live_win.py --window 5 --refresh-ms 100
    python emg_live_win.py --host 172.16.212.170 --user orangepi
"""
import argparse
import struct
import subprocess
import sys
import threading
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# Packet layout — must match emg_viewer.py / ads1298_stream.c v0x02
EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
EMG_PKT_LEN = 64
EMG_DEV_LEN = 27
EMG_DEV_COUNT = 2
EMG_CH_PER_DEV = 8
EMG_TOTAL_CH = 16
FRAME_HEADER_SIZE = 8                       # host_recv_ns prefix
RECORD_LEN = FRAME_HEADER_SIZE + EMG_PKT_LEN  # 72 bytes/record
EMG_SAMPLE_RATE_HZ = 2000

DEFAULT_HOST = "172.16.212.170"
DEFAULT_USER = "orangepi"
DEFAULT_DATA = "/home/orangepi/sensor_host/data"
DEFAULT_LISTEN_PORT = 3333


def _int24_be(b):
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    if v & 0x800000:
        v -= 0x1000000
    return v


def _shift_left_1bit_27(buf):
    """Daisy-chain dead-bit compensation for chip B's 27 bytes."""
    out = bytearray(27)
    for i in range(26):
        out[i] = ((buf[i] << 1) & 0xFF) | (buf[i + 1] >> 7)
    out[26] = (buf[26] << 1) & 0xFF
    return bytes(out)


def find_latest_bin(host, user, data_dir):
    cmd = ["ssh", f"{user}@{host}",
           f"ls -t {data_dir}/emg_*.bin 2>/dev/null | head -1"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    out = r.stdout.strip()
    if not out:
        raise RuntimeError(f"no emg_*.bin under {data_dir} on {host}")
    return out


def decode_record(record, ch_buffers, lock):
    """Decode one 72-byte record into 16 channel samples; append to deques."""
    po = FRAME_HEADER_SIZE
    if record[po] != EMG_HDR or record[po + EMG_PKT_LEN - 1] != EMG_FTR:
        return False
    chip_a = bytes(record[po + 9 : po + 9 + EMG_DEV_LEN])
    chip_b = _shift_left_1bit_27(bytes(record[po + 9 + EMG_DEV_LEN : po + 9 + 54]))
    samples = [0] * EMG_TOTAL_CH
    for d_idx, frame in enumerate((chip_a, chip_b)):
        for ch in range(EMG_CH_PER_DEV):
            so = 3 + ch * 3
            samples[d_idx * EMG_CH_PER_DEV + ch] = _int24_be(frame[so:so + 3])
    with lock:
        for ch in range(EMG_TOTAL_CH):
            ch_buffers[ch].append(samples[ch])
    return True


def _looks_like_record_start(buf, idx):
    """Check whether buf[idx:idx+RECORD_LEN] looks like a valid EMG record."""
    if idx + RECORD_LEN > len(buf):
        return False
    return (buf[idx + FRAME_HEADER_SIZE] == EMG_HDR and
            buf[idx + RECORD_LEN - 1] == EMG_FTR)


def tcp_server_thread(port, ch_buffers, lock, stop_flag, stats,
                      record_fp=None):
    """Listen on TCP :port, accept ESP32 connection, decode in real time.

    Wire format on the socket is the 64-byte EMG packet the ESP32 sends.
    For each socket recv() we batch-decode every complete record, then
    acquire the lock exactly ONCE and `extend` all 16 deques. Lock rate
    drops from ~2000/s (per-record) to ~15/s (per-chunk) — that was the
    `good +1500/s` ceiling.

    If record_fp is given, each successfully decoded record is also written
    to disk prefixed with 8 B host_recv_ns, matching sensor-host's .bin
    format so the file is directly playable by emg_viewer.py --file.
    """
    import socket
    import time
    WIRE_REC_LEN = EMG_PKT_LEN  # 64 bytes on the wire

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)
    srv.settimeout(0.5)
    print(f"TCP server listening on 0.0.0.0:{port}")
    if record_fp:
        print(f"recording to {record_fp.name}")

    while not stop_flag.is_set():
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        print(f"ESP32 connected from {addr[0]}:{addr[1]}")
        conn.settimeout(2.0)
        buf = bytearray()
        rd = 0
        synced = False
        COMPACT_AT = 64 * 1024

        # Per-chunk scratch: 16 lists we extend into the deques in one lock
        ch_local = [[] for _ in range(EMG_TOTAL_CH)]
        record_writes = []  # (ts_ns, record_bytes) tuples for this chunk
        try:
            while not stop_flag.is_set():
                try:
                    chunk = conn.recv(8192)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf.extend(chunk)

                # Drain all complete records from this chunk into ch_local
                while len(buf) - rd >= WIRE_REC_LEN:
                    if not synced:
                        found = -1
                        limit = len(buf) - WIRE_REC_LEN
                        while rd <= limit:
                            if (buf[rd] == EMG_HDR and
                                    buf[rd + WIRE_REC_LEN - 1] == EMG_FTR):
                                found = rd
                                break
                            rd += 1
                        if found < 0:
                            stats["bad"] += 1
                            break
                        synced = True
                    if (buf[rd] != EMG_HDR or
                            buf[rd + WIRE_REC_LEN - 1] != EMG_FTR):
                        rd += 1
                        synced = False
                        stats["bad"] += 1
                        continue
                    record = bytes(buf[rd : rd + WIRE_REC_LEN])
                    rd += WIRE_REC_LEN

                    chip_a = record[9 : 9 + EMG_DEV_LEN]
                    chip_b = _shift_left_1bit_27(
                        record[9 + EMG_DEV_LEN : 9 + 54])
                    for d_idx, frame in enumerate((chip_a, chip_b)):
                        base_ch = d_idx * EMG_CH_PER_DEV
                        for ch in range(EMG_CH_PER_DEV):
                            so = 3 + ch * 3
                            ch_local[base_ch + ch].append(
                                _int24_be(frame[so:so + 3]))
                    stats["good"] += 1
                    if record_fp is not None:
                        record_writes.append((time.time_ns(), record))

                # End of chunk: ONE lock, batch extend.
                if ch_local[0]:
                    with lock:
                        for ch in range(EMG_TOTAL_CH):
                            ch_buffers[ch].extend(ch_local[ch])
                            ch_local[ch].clear()

                # File write outside the deque lock.
                if record_writes:
                    for ts_ns, rec in record_writes:
                        record_fp.write(ts_ns.to_bytes(8, "little"))
                        record_fp.write(rec)
                    record_writes.clear()
                    # flush periodically so a crash doesn't lose >1s of data
                    if stats["good"] % 4096 < 256:
                        record_fp.flush()

                if rd >= COMPACT_AT:
                    del buf[:rd]
                    rd = 0
        finally:
            try: conn.close()
            except Exception: pass
            print("ESP32 disconnected, waiting for reconnect...")

    try: srv.close()
    except Exception: pass


def stream_thread(host, user, path, ch_buffers, lock, stop_flag, stats):
    """Background: SSH tail the remote .bin and feed decoded samples into ringbufs.

    Performance: instead of `del buf[:N]` after every 72-byte record (each
    one an O(buf_size) memmove → bottlenecked us to ~1000 rec/s on a 2000 sps
    stream), we keep a read index into a growing bytearray and only compact
    when the head accumulates past 64 KB. This drops the per-record cost from
    "memmove of 8 KB" to "two integer adds".
    """
    cmd = ["ssh",
           "-o", "ServerAliveInterval=10",
           "-o", "ServerAliveCountMax=3",
           f"{user}@{host}",
           f"tail -c 0 -F {path}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=0)
    buf = bytearray()
    rd = 0           # read index into buf
    synced = False
    COMPACT_AT = 64 * 1024
    try:
        while not stop_flag.is_set():
            chunk = proc.stdout.read(8192)
            if not chunk:
                break
            buf.extend(chunk)

            while len(buf) - rd >= RECORD_LEN:
                if not synced:
                    # byte-walk to find first record boundary
                    found = -1
                    limit = len(buf) - RECORD_LEN
                    while rd <= limit:
                        if (buf[rd + FRAME_HEADER_SIZE] == EMG_HDR and
                                buf[rd + RECORD_LEN - 1] == EMG_FTR):
                            found = rd
                            break
                        rd += 1
                    if found < 0:
                        stats["bad"] += 1
                        break
                    synced = True

                # synced path — cheap check on this candidate
                if (buf[rd + FRAME_HEADER_SIZE] != EMG_HDR or
                        buf[rd + RECORD_LEN - 1] != EMG_FTR):
                    rd += 1
                    synced = False
                    stats["bad"] += 1
                    continue

                record = bytes(buf[rd : rd + RECORD_LEN])
                rd += RECORD_LEN
                if decode_record(record, ch_buffers, lock):
                    stats["good"] += 1
                else:
                    stats["bad"] += 1
                    synced = False

            # compact buf head occasionally so memory doesn't grow unbounded
            if rd >= COMPACT_AT:
                del buf[:rd]
                rd = 0
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", action="store_true",
                    help="run as TCP server (ESP32 connects to us directly); "
                         "default is SSH-tail mode")
    ap.add_argument("--port", type=int, default=DEFAULT_LISTEN_PORT,
                    help=f"TCP listen port (default {DEFAULT_LISTEN_PORT})")
    ap.add_argument("--record", metavar="FILE",
                    help="record raw stream to FILE (sensor-host .bin format: "
                         "8B host_recv_ns + 64B packet per record). Replayable "
                         "with emg_viewer.py --file FILE.")
    ap.add_argument("--record-auto", action="store_true",
                    help="record to emg_DIRECT_<timestamp>.bin in cwd")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--user", default=DEFAULT_USER)
    ap.add_argument("--data-dir", default=DEFAULT_DATA)
    ap.add_argument("--window", type=float, default=5.0,
                    help="seconds of history per channel (default 5)")
    ap.add_argument("--refresh-ms", type=int, default=250,
                    help="plot refresh interval ms (default 250)")
    ap.add_argument("--decimate", type=int, default=4,
                    help="downsample factor for display (default 4 -> 500 Hz)")
    ap.add_argument("--sps", type=float, default=EMG_SAMPLE_RATE_HZ)
    args = ap.parse_args()

    window_samples = int(args.window * args.sps)
    ch_buffers = [deque(maxlen=window_samples) for _ in range(EMG_TOTAL_CH)]
    lock = threading.Lock()
    stop_flag = threading.Event()
    stats = {"good": 0, "bad": 0}

    if args.listen:
        path = f"TCP :{args.port}"
        # Open record file before spawning thread so any I/O error is loud.
        record_fp = None
        if args.record:
            record_fp = open(args.record, "ab", buffering=0)
            print(f"recording to {args.record}")
        elif args.record_auto:
            from datetime import datetime
            fname = f"emg_DIRECT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bin"
            record_fp = open(fname, "ab", buffering=0)
            print(f"auto-recording to {fname}")
        t = threading.Thread(target=tcp_server_thread,
                             args=(args.port, ch_buffers, lock,
                                   stop_flag, stats, record_fp),
                             daemon=True)
    else:
        print(f"locating latest .bin on {args.user}@{args.host}:{args.data_dir} ...")
        try:
            path = find_latest_bin(args.host, args.user, args.data_dir)
        except Exception as e:
            print(f"error: {e}")
            return 1
        print(f"streaming {path}")
        t = threading.Thread(target=stream_thread,
                             args=(args.host, args.user, path,
                                   ch_buffers, lock, stop_flag, stats),
                             daemon=True)
    t.start()

    dec = max(1, int(args.decimate))
    disp_samples = window_samples // dec  # x-axis range after decimation

    fig, axes = plt.subplots(4, 4, figsize=(16, 9), sharex=True)
    title_artist = fig.suptitle("starting...", fontsize=11)
    lines = []
    # Pre-fix axes: don't autoscale per frame — that's what was making it
    # janky (each set_ylim forces a full redraw of axes + labels).
    INITIAL_YLIM = (-2_000_000.0, 2_000_000.0)  # 24-bit signed half-range / 4
    for ch in range(EMG_TOTAL_CH):
        ax = axes[ch // 4, ch % 4]
        chip = "A" if ch < 8 else "B"
        color = "tab:blue" if ch < 8 else "tab:orange"
        line, = ax.plot([], [], color=color, lw=0.6)
        ax.set_title(f"Chip {chip} ch{ch % 8 + 1} (idx {ch})", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        ax.set_xlim(0, disp_samples)
        ax.set_ylim(*INITIAL_YLIM)
        if ch >= 12:
            ax.set_xlabel(f"samples ÷{dec}", fontsize=8)
        if ch % 4 == 0:
            ax.set_ylabel("ADC", fontsize=8)
        lines.append(line)
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    # Per-channel auto-zoom counter — only re-fit ylim every N frames, not
    # every frame, to keep redraw cost low.
    rescale_period = 8  # every ~2 s at 250 ms refresh
    frame_idx = [0]

    def update(_frame):
        frame_idx[0] += 1
        do_rescale = (frame_idx[0] % rescale_period) == 0
        with lock:
            for ch, line in enumerate(lines):
                src = ch_buffers[ch]
                if not src:
                    continue
                y_full = np.fromiter(src, dtype=np.float32, count=len(src))
                # Decimate by simple stride for display only — the raw
                # samples in the deque are untouched.
                y = y_full[::dec]
                x = np.arange(y.size)
                line.set_data(x, y)
                if do_rescale and y.size > 4:
                    lo, hi = float(y.min()), float(y.max())
                    rng = hi - lo
                    pad = max(10.0, 0.10 * rng)
                    axes[ch // 4, ch % 4].set_ylim(lo - pad, hi + pad)
        title_artist.set_text(
            f"EMG live · {path} · win={args.window}s · dec={dec} · "
            f"good={stats['good']} bad={stats['bad']}")
        return lines

    try:
        ani = FuncAnimation(fig, update, interval=args.refresh_ms,
                            blit=False, cache_frame_data=False)
        plt.show()
    finally:
        stop_flag.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
