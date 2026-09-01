#!/usr/bin/env python3
"""Real-time 16-channel EMG viewer (PyQtGraph backend).

Same protocol as emg_live_win.py — listens on TCP :3333 for ESP32 to connect
direct over WiFi — but uses PyQtGraph instead of matplotlib so 16 channels at
2 kHz stay smooth (PyQtGraph paths through OpenGL / GPU rasterisation;
matplotlib redraws the entire figure every frame on CPU).

Usage:
    python emg_live_qt.py                       # default: TCP :3333
    python emg_live_qt.py --record session.bin  # also dump raw stream
    python emg_live_qt.py --record-auto         # auto-name emg_DIRECT_*.bin
    python emg_live_qt.py --window 3            # 3-second history
"""
import argparse
import os
import socket
import struct
import sys
import threading
import time
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

# --- Packet layout — must match ads1298_stream.c v0x02 ---------------------
EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
EMG_PKT_LEN = 64
EMG_DEV_LEN = 27
EMG_DEV_COUNT = 2
EMG_CH_PER_DEV = 8
EMG_TOTAL_CH = 16
EMG_SAMPLE_RATE_HZ = 2000
DEFAULT_PORT = 3333
DEFAULT_LOG_DIR = r"C:\work1\JSZN\ESP32_S3\ESP32-S3\log"


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


# --- Ring buffer ---------------------------------------------------------
class ChannelRingBuffer:
    """Fixed-size numpy ring buffer for one channel. Lock-free writer +
    lock-protected get-snapshot for the reader. Used per-channel so each
    channel's writer/reader stays independent."""

    def __init__(self, size: int):
        self.size = size
        self.buf = np.zeros(size, dtype=np.int32)
        self.write_idx = 0
        self.wrapped = False  # has any wrap happened?

    def extend(self, samples):
        """Write a flat list/array of samples."""
        n = len(samples)
        if n == 0:
            return
        if n >= self.size:
            samples = samples[-self.size:]
            n = self.size
        end = self.write_idx + n
        if end <= self.size:
            self.buf[self.write_idx:end] = samples
        else:
            first = self.size - self.write_idx
            self.buf[self.write_idx:] = samples[:first]
            self.buf[:n - first] = samples[first:]
            self.wrapped = True
        self.write_idx = end % self.size
        if end >= self.size:
            self.wrapped = True

    def snapshot(self):
        """Return a contiguous numpy array of the current visible window,
        oldest-first. No copy of channel data beyond np.concatenate when wrapped."""
        if not self.wrapped:
            return self.buf[:self.write_idx].copy()
        return np.concatenate(
            (self.buf[self.write_idx:], self.buf[:self.write_idx])
        )


# --- TCP server (background thread) -------------------------------------
class StreamReader(threading.Thread):
    def __init__(self, port: int, ch_bufs, stats):
        super().__init__(daemon=True)
        self.port = port
        self.ch_bufs = ch_bufs
        self.stats = stats
        self.stop_flag = threading.Event()
        self.client_addr = None
        self.listening = False

        # Runtime-controllable knobs (set by GUI via plain attribute writes,
        # protected by a single re-entrant lock for swap atomicity).
        self._lock = threading.Lock()
        self._record_fp = None
        self._record_bytes = 0
        self._record_sample_idx = 0
        self._accept_enabled = True
        self._active_conn = None

    # ---- GUI-facing controls ----
    def set_record_file(self, fp, fs=EMG_SAMPLE_RATE_HZ):
        """Swap the record-file handle. Pass None to stop recording.

        File is CSV: metadata header lines starting with '#' (pandas-friendly
        via comment='#'), then column header, then one row per ADS1298 sample
        with columns: sample_idx, t_s, timestamp_ns, ch0..ch15.
        """
        with self._lock:
            old = self._record_fp
            self._record_fp = fp
            self._record_bytes = 0
            self._record_sample_idx = 0
            if fp is not None:
                meta = (
                    f"# emg_live_qt record\n"
                    f"# start_iso={datetime.now().isoformat()}\n"
                    f"# fs={fs}\n"
                    f"# channels={EMG_TOTAL_CH}\n"
                    f"# chip_a=ch0..ch7  chip_b=ch8..ch15\n"
                )
                fp.write(meta.encode("utf-8"))
                header = ("sample_idx,t_s,timestamp_ns,seq," +
                          ",".join(f"ch{i}" for i in range(EMG_TOTAL_CH)) +
                          "\n")
                fp.write(header.encode("utf-8"))
                self._record_bytes = len(meta) + len(header)
        if old is not None and old is not fp:
            try:
                old.flush(); old.close()
            except Exception:
                pass

    def get_record_status(self):
        with self._lock:
            if self._record_fp is None:
                return (None, 0)
            return (self._record_fp.name, self._record_bytes)

    def set_accept_enabled(self, enabled: bool):
        """When False, any incoming connection is closed immediately (and
        the active one too). When True, new connections are accepted normally."""
        self._accept_enabled = enabled
        if not enabled:
            conn = self._active_conn
            if conn is not None:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass

    def run(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.port))
        srv.listen(1)
        srv.settimeout(0.5)
        self.listening = True
        print(f"TCP server listening on 0.0.0.0:{self.port}")

        while not self.stop_flag.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            if not self._accept_enabled:
                try:
                    conn.close()
                except Exception:
                    pass
                continue

            self.client_addr = f"{addr[0]}:{addr[1]}"
            self._active_conn = conn
            print(f"ESP32 connected from {self.client_addr}")
            try:
                self._read_loop(conn)
            except Exception as e:
                print(f"reader error: {e}")
            finally:
                self._active_conn = None
                try:
                    conn.close()
                except Exception:
                    pass
                print("ESP32 disconnected, waiting for reconnect...")
                self.client_addr = None
        try:
            srv.close()
        except Exception:
            pass

    def _read_loop(self, conn):
        conn.settimeout(0.5)
        buf = bytearray()
        rd = 0
        synced = False
        COMPACT_AT = 64 * 1024
        WIRE_REC_LEN = EMG_PKT_LEN
        ch_local = [[] for _ in range(EMG_TOTAL_CH)]
        record_writes = []

        while not self.stop_flag.is_set():
            if not self._accept_enabled:
                # GUI clicked Disconnect — drop this connection.
                return
            try:
                chunk = conn.recv(8192)
            except socket.timeout:
                continue
            if not chunk:
                return
            buf.extend(chunk)

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
                        self.stats["bad"] += 1
                        break
                    synced = True

                if (buf[rd] != EMG_HDR or
                        buf[rd + WIRE_REC_LEN - 1] != EMG_FTR):
                    rd += 1
                    synced = False
                    self.stats["bad"] += 1
                    continue

                record = bytes(buf[rd : rd + WIRE_REC_LEN])
                rd += WIRE_REC_LEN

                # Packet header (offset relative to start of 64-byte record):
                #   [0]=0xAA  [1]=ver  [2..3]=seq (LE)  [4..7]=mcu_ts_us  [8]=nDev
                seq = record[2] | (record[3] << 8)
                chip_a = record[9 : 9 + EMG_DEV_LEN]
                chip_b = _shift_left_1bit_27(
                    record[9 + EMG_DEV_LEN : 9 + 54])
                samples_16 = [0] * EMG_TOTAL_CH
                for d_idx, frame in enumerate((chip_a, chip_b)):
                    base_ch = d_idx * EMG_CH_PER_DEV
                    for ch in range(EMG_CH_PER_DEV):
                        so = 3 + ch * 3
                        v = _int24_be(frame[so:so + 3])
                        ch_local[base_ch + ch].append(v)
                        samples_16[base_ch + ch] = v
                self.stats["good"] += 1
                if self._record_fp is not None:
                    record_writes.append((time.time_ns(), seq, samples_16))

            # Batch push into ring buffers (lock-free — single writer).
            if ch_local[0]:
                for ch in range(EMG_TOTAL_CH):
                    self.ch_bufs[ch].extend(ch_local[ch])
                    ch_local[ch].clear()

            if record_writes:
                # Re-check the file inside the lock — GUI may have swapped it.
                with self._lock:
                    fp = self._record_fp
                    base_idx = self._record_sample_idx
                if fp is not None:
                    lines = []
                    fs = EMG_SAMPLE_RATE_HZ
                    for i, (ts_ns, seq, samples) in enumerate(record_writes):
                        idx = base_idx + i
                        t_s = idx / fs
                        lines.append(
                            f"{idx},{t_s:.6f},{ts_ns},{seq},"
                            f"{','.join(str(s) for s in samples)}\n"
                        )
                    blob = "".join(lines).encode("utf-8")
                    fp.write(blob)
                    with self._lock:
                        if self._record_fp is fp:  # not swapped mid-write
                            self._record_bytes += len(blob)
                            self._record_sample_idx += len(record_writes)
                    if self.stats["good"] % 4096 < 256:
                        try: fp.flush()
                        except Exception: pass
                record_writes.clear()

            if rd >= COMPACT_AT:
                del buf[:rd]
                rd = 0


# --- GUI ----------------------------------------------------------------
class EMGWindow(QtWidgets.QMainWindow):
    def __init__(self, ch_bufs, stats, reader: StreamReader,
                 window_seconds: float, sps: float, refresh_ms: int,
                 decimate: int, port: int):
        super().__init__()
        self.setWindowTitle(f"EMG live (PyQtGraph) — listening on :{port}")
        self.resize(1600, 950)
        self.ch_bufs = ch_bufs
        self.stats = stats
        self.reader = reader
        self.port = port
        self.decimate = max(1, decimate)
        self.disp_samples = int(window_seconds * sps) // self.decimate

        central = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # ---- Toolbar row ----
        tb = QtWidgets.QHBoxLayout()
        tb.setSpacing(8)

        self.connect_btn = QtWidgets.QPushButton("Disconnect")
        self.connect_btn.setMinimumWidth(110)
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        tb.addWidget(self.connect_btn)

        self.record_btn = QtWidgets.QPushButton("开始录制")
        self.record_btn.setMinimumWidth(110)
        self.record_btn.clicked.connect(self._on_record_clicked)
        tb.addWidget(self.record_btn)

        tb.addWidget(QtWidgets.QLabel("Y 轴范围:"))
        self.yrange_combo = QtWidgets.QComboBox()
        for label, val in [("auto", 0), ("±1e4", 1e4), ("±1e5", 1e5),
                           ("±5e5", 5e5), ("±1e6", 1e6), ("±5e6", 5e6),
                           ("±1e7", 1e7)]:
            self.yrange_combo.addItem(label, val)
        self.yrange_combo.setCurrentIndex(0)
        self.yrange_combo.currentIndexChanged.connect(self._on_yrange_changed)
        tb.addWidget(self.yrange_combo)

        tb.addWidget(QtWidgets.QLabel("窗口(s):"))
        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.window_spin.setRange(0.5, 30.0)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setDecimals(1)
        self.window_spin.setValue(window_seconds)
        self.window_spin.valueChanged.connect(self._on_window_changed)
        tb.addWidget(self.window_spin)

        tb.addStretch(1)

        self.status_label = QtWidgets.QLabel("starting...")
        self.status_label.setStyleSheet(
            "font-family: Consolas; font-size: 10pt;")
        tb.addWidget(self.status_label)
        v.addLayout(tb)

        # ---- Plot grid ----
        glw = pg.GraphicsLayoutWidget()
        v.addWidget(glw, 1)
        self.setCentralWidget(central)

        self.curves = []
        self.plots = []
        for ch in range(EMG_TOTAL_CH):
            r, c = ch // 4, ch % 4
            chip = "A" if ch < 8 else "B"
            color = (66, 135, 245) if ch < 8 else (245, 142, 60)
            p = glw.addPlot(row=r, col=c,
                            title=f"Chip {chip} ch{ch % 8 + 1} (idx {ch})")
            p.showGrid(x=True, y=True, alpha=0.3)
            p.setMouseEnabled(x=False, y=False)
            p.hideButtons()
            p.setDownsampling(auto=True, mode="peak")
            p.setClipToView(True)
            p.setXRange(0, self.disp_samples, padding=0)
            curve = p.plot(pen=pg.mkPen(color=color, width=1))
            self.curves.append(curve)
            self.plots.append(p)

        self.sps = sps
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(refresh_ms)
        self._last_stats = (0, 0, time.monotonic())
        self._sps_fixed_y = 0  # 0 = auto; else fixed ±value

    # ---- Button slots ----
    def _on_connect_clicked(self):
        enabled = not self.reader._accept_enabled
        self.reader.set_accept_enabled(enabled)
        self.connect_btn.setText("Disconnect" if enabled else "Connect")

    def _on_record_clicked(self):
        name, _ = self.reader.get_record_status()
        if name is None:
            # Start recording immediately — no file dialog. Path is auto-
            # generated under DEFAULT_LOG_DIR using a timestamp + fs tag.
            try:
                os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = os.path.join(
                    DEFAULT_LOG_DIR,
                    f"emg_{ts}_fs{int(EMG_SAMPLE_RATE_HZ)}.csv"
                )
                fp = open(fname, "ab", buffering=0)
            except Exception as e:
                self.status_label.setText(f"录制启动失败: {e}")
                return
            self.reader.set_record_file(fp)
            self.record_btn.setText("停止录制")
            self.record_btn.setStyleSheet(
                "background-color: #c62828; color: white;")
        else:
            self.reader.set_record_file(None)
            self.record_btn.setText("开始录制")
            self.record_btn.setStyleSheet("")

    def _on_yrange_changed(self, _idx):
        val = self.yrange_combo.currentData()
        self._sps_fixed_y = float(val) if val else 0
        if self._sps_fixed_y:
            for p in self.plots:
                p.setYRange(-self._sps_fixed_y, self._sps_fixed_y, padding=0)
                p.enableAutoRange(axis='y', enable=False)
        else:
            for p in self.plots:
                p.enableAutoRange(axis='y', enable=True)

    def _on_window_changed(self, val):
        self.disp_samples = int(val * self.sps) // self.decimate
        for p in self.plots:
            p.setXRange(0, self.disp_samples, padding=0)

    def _refresh(self):
        now = time.monotonic()
        last_good, last_bad, last_t = self._last_stats
        dt = now - last_t
        rate = (self.stats["good"] - last_good) / dt if dt > 0 else 0.0
        self._last_stats = (self.stats["good"], self.stats["bad"], now)

        client = self.reader.client_addr or "-"
        rec_name, rec_bytes = self.reader.get_record_status()
        if rec_name:
            short = rec_name.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            rec_str = f"  REC: {short} ({rec_bytes/1024:.1f} KB)"
        else:
            rec_str = ""
        self.status_label.setText(
            f"client={client}  good={self.stats['good']}  "
            f"bad={self.stats['bad']}  rate={rate:7.1f}/s{rec_str}"
        )

        for ch in range(EMG_TOTAL_CH):
            y_full = self.ch_bufs[ch].snapshot()
            if y_full.size == 0:
                continue
            y = y_full[::self.decimate]
            x = np.arange(y.size, dtype=np.int32)
            self.curves[ch].setData(x, y)

    def closeEvent(self, event):
        # Make sure we don't leak the record file.
        self.reader.set_record_file(None)
        super().closeEvent(event)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--window", type=float, default=5.0,
                    help="seconds of history per channel")
    ap.add_argument("--sps", type=float, default=EMG_SAMPLE_RATE_HZ)
    ap.add_argument("--refresh-ms", type=int, default=33,
                    help="refresh interval ms (default 33 ≈ 30 fps)")
    ap.add_argument("--decimate", type=int, default=2,
                    help="display-only decimation factor (default 2)")
    ap.add_argument("--record", metavar="FILE",
                    help="record raw stream (sensor-host .bin format)")
    ap.add_argument("--record-auto", action="store_true",
                    help="record to emg_DIRECT_<timestamp>.bin in cwd")
    args = ap.parse_args()

    window_samples = int(args.window * args.sps)
    ch_bufs = [ChannelRingBuffer(window_samples) for _ in range(EMG_TOTAL_CH)]
    stats = {"good": 0, "bad": 0}

    reader = StreamReader(args.port, ch_bufs, stats)
    reader.start()

    # Initial record file if user passed CLI flag (button can still toggle).
    if args.record:
        reader.set_record_file(open(args.record, "ab", buffering=0))
    elif args.record_auto:
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
        fname = os.path.join(
            DEFAULT_LOG_DIR,
            f"emg_DIRECT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        reader.set_record_file(open(fname, "ab", buffering=0))

    app = QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=False, useOpenGL=False)
    win = EMGWindow(ch_bufs, stats, reader,
                    window_seconds=args.window, sps=args.sps,
                    refresh_ms=args.refresh_ms,
                    decimate=args.decimate, port=args.port)
    # Reflect any CLI-supplied recording in the button.
    if args.record or args.record_auto:
        win.record_btn.setText("停止录制")
        win.record_btn.setStyleSheet(
            "background-color: #c62828; color: white;")
    win.show()
    rc = app.exec_()
    reader.stop_flag.set()
    reader.set_record_file(None)
    sys.exit(rc)


if __name__ == "__main__":
    main()
