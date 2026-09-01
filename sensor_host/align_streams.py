#!/usr/bin/env python3
"""Offline EMG + IMU stream alignment with MCU<->Host linear regression.

Per the time-sync approach in the article:
    host_ns = slope * mcu_ts_continuous + intercept
where mcu_ts_continuous is the wrap-corrected uint32 us-since-boot counter.

Quality gates (article §9):
  - >= 10 sample pairs
  - regression residual std < 50 ms
  - mcu_ts not all zero
Fallback when any gate fails: use host_recv_ns directly as canonical time.

Outputs per session:
  aligned_emg.npz  (samples [N,16], mcu_ts_us [N], mcu_ts_continuous_us [N],
                    host_recv_ns [N], canonical_ts_ns [N], seq [N], status [N,2])
  aligned_imu.npz  (samples [M,9], mcu_ts_us [P], mcu_ts_continuous_us [P],
                    host_recv_pkt_ns [P], canonical_ts_ns [P], seq [P])
                    NOTE: timestamps are per-packet; M = P*10 individual samples
                    with linearly interpolated within-packet timing.
  aligned_report.txt   timing health + regression quality
"""
import argparse
import logging
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# ---------- packet layouts (matches actual firmware) ----------
EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
EMG_PKT_LEN = 64
EMG_DEV_LEN = 27
EMG_DEV_COUNT = 2
EMG_CH_PER_DEV = 8
EMG_TOTAL_CH = EMG_DEV_COUNT * EMG_CH_PER_DEV  # 16

IMU_HDR, IMU_VER, IMU_TYPE = 0xBB, 0x01, 0x20
IMU_PKT_LEN = 211
IMU_SAMPLES_PER_PKT = 10
IMU_SAMPLE_RATE_HZ = 200

FRAME_HEADER_SIZE = 8  # host_recv_ns prefix
MCU_TS_BITS = 32
MCU_TS_MAX = 1 << MCU_TS_BITS  # 2^32 us = ~71.6 minutes


def _int24_be(b: bytes) -> int:
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    if v & 0x800000:
        v -= 0x1000000
    return v


def _shift_left_1bit(buf: bytes) -> bytes:
    """ADS1298 daisy chain inserts a 'don't care' bit between each device's
    216-bit frame. Firmware reads 54 bytes straight, so chip A is correct but
    chip B comes out right-shifted by 1 bit. Apply left-shift here.

    Input: chip B's raw 27 bytes (plus 1 borrow byte from the next packet's
    first byte for the final bit). Returns 27 shifted bytes.
    If no borrow byte is provided, the last bit is set to 0.
    """
    out = bytearray(27)
    for i in range(26):
        out[i] = ((buf[i] << 1) & 0xFF) | (buf[i + 1] >> 7)
    out[26] = (buf[26] << 1) & 0xFF
    return bytes(out)


def unwrap_mcu_ts(ts_raw: np.ndarray) -> np.ndarray:
    """Detect 32-bit wraps and return monotonic int64 continuous counter (us)."""
    if len(ts_raw) == 0:
        return ts_raw.astype(np.int64)
    out = np.empty(len(ts_raw), dtype=np.int64)
    wraps = 0
    last = -1
    for i, v in enumerate(ts_raw):
        vi = int(v)
        if last != -1 and vi < last and (last - vi) > MCU_TS_MAX // 2:
            wraps += 1
        out[i] = wraps * MCU_TS_MAX + vi
        last = vi
    return out


def parse_emg_file(path: Path, log: logging.Logger):
    data = path.read_bytes()
    record_len = FRAME_HEADER_SIZE + EMG_PKT_LEN
    n = len(data) // record_len
    if n == 0:
        log.warning("%s: empty", path)
        return None

    mcu_ts_raw = np.empty(n, dtype=np.uint32)
    host_recv = np.empty(n, dtype=np.uint64)
    seq = np.empty(n, dtype=np.uint16)
    statuses = np.empty((n, EMG_DEV_COUNT), dtype=np.uint32)
    samples = np.empty((n, EMG_TOTAL_CH), dtype=np.int32)

    write_idx = 0
    for i in range(n):
        off = i * record_len
        host_recv[write_idx] = struct.unpack_from("<Q", data, off)[0]
        pkt_off = off + FRAME_HEADER_SIZE
        if (data[pkt_off] != EMG_HDR or data[pkt_off + 1] != EMG_VER
                or data[pkt_off + EMG_PKT_LEN - 1] != EMG_FTR):
            log.warning("skip bad EMG frame at idx=%d", i)
            continue
        seq[write_idx] = struct.unpack_from("<H", data, pkt_off + 2)[0]
        mcu_ts_raw[write_idx] = struct.unpack_from("<I", data, pkt_off + 4)[0]
        # Chip A: raw bytes
        chip_a = bytes(data[pkt_off + 9 : pkt_off + 9 + EMG_DEV_LEN])
        # Chip B: raw bytes shifted left 1 bit to compensate for daisy chain dead bit
        chip_b_raw = bytes(data[pkt_off + 9 + EMG_DEV_LEN : pkt_off + 9 + 2 * EMG_DEV_LEN])
        chip_b = _shift_left_1bit(chip_b_raw)
        for d, frame in enumerate((chip_a, chip_b)):
            statuses[write_idx, d] = int.from_bytes(frame[0:3], "big")
            for ch in range(EMG_CH_PER_DEV):
                so = 3 + ch * 3
                samples[write_idx, d * EMG_CH_PER_DEV + ch] = _int24_be(frame[so:so + 3])
        write_idx += 1

    if write_idx < n:
        log.warning("%s: kept %d / %d frames", path.name, write_idx, n)
    return {
        "mcu_ts_raw": mcu_ts_raw[:write_idx],
        "host_recv_ns": host_recv[:write_idx],
        "seq": seq[:write_idx],
        "status": statuses[:write_idx],
        "samples": samples[:write_idx],
    }


def parse_imu_file(path: Path, log: logging.Logger):
    data = path.read_bytes()
    record_len = FRAME_HEADER_SIZE + IMU_PKT_LEN
    n_pkts = len(data) // record_len
    if n_pkts == 0:
        log.warning("%s: empty", path)
        return None

    mcu_ts_raw = np.empty(n_pkts, dtype=np.uint32)
    host_recv = np.empty(n_pkts, dtype=np.uint64)
    seq = np.empty(n_pkts, dtype=np.uint16)
    samples_per_pkt = np.empty((n_pkts, IMU_SAMPLES_PER_PKT, 9), dtype=np.int16)

    write_idx = 0
    for i in range(n_pkts):
        off = i * record_len
        host_recv[write_idx] = struct.unpack_from("<Q", data, off)[0]
        pkt_off = off + FRAME_HEADER_SIZE
        if (data[pkt_off] != IMU_HDR or data[pkt_off + 1] != IMU_VER
                or data[pkt_off + 2] != IMU_TYPE
                or data[pkt_off + IMU_PKT_LEN - 1] != EMG_FTR):
            log.warning("skip bad IMU frame at idx=%d", i)
            continue
        seq[write_idx] = struct.unpack_from("<H", data, pkt_off + 3)[0]
        mcu_ts_raw[write_idx] = struct.unpack_from("<I", data, pkt_off + 5)[0]
        block = np.frombuffer(
            data, dtype="<i2",
            count=IMU_SAMPLES_PER_PKT * 10, offset=pkt_off + 10,
        ).reshape(IMU_SAMPLES_PER_PKT, 10)
        samples_per_pkt[write_idx] = block[:, :9]
        write_idx += 1

    return {
        "mcu_ts_raw": mcu_ts_raw[:write_idx],
        "host_recv_ns": host_recv[:write_idx],
        "seq": seq[:write_idx],
        "samples_per_pkt": samples_per_pkt[:write_idx],
    }


# ---------- linear regression with quality gates ----------
@dataclass
class RegressionResult:
    slope: float            # ns per us (should be ~1000.0 for nominal MCU clock)
    intercept_ns: float
    residual_std_ns: float
    n: int
    passed: bool
    reason: str             # why it passed/failed

    def apply(self, mcu_ts_us: np.ndarray) -> np.ndarray:
        return (self.slope * mcu_ts_us.astype(np.float64) + self.intercept_ns).astype(np.int64)


def fit_mcu_to_host(mcu_us_continuous: np.ndarray, host_ns: np.ndarray,
                    log: logging.Logger, name: str,
                    host_ns_for_filter: np.ndarray | None = None,
                    batch_filter_threshold_ms: float = 5.0) -> RegressionResult:
    """Linear regression with article's quality gates.

    If host inter-arrival shows clear batches (gap > batch_filter_threshold_ms),
    we ALSO compute a second-pass regression using only the first packet of each
    batch -- this removes batch-send artifacts and gives the "real" sync accuracy.
    """
    n = len(mcu_us_continuous)
    if n < 10:
        log.warning("%s: regression fallback - only %d samples (<10)", name, n)
        return RegressionResult(1000.0, 0.0, 0.0, n, False, "too_few_samples")
    if np.all(mcu_us_continuous == 0):
        log.warning("%s: regression fallback - all mcu_ts are zero", name)
        return RegressionResult(1000.0, 0.0, 0.0, n, False, "mcu_ts_all_zero")

    x = mcu_us_continuous.astype(np.float64)
    y = host_ns.astype(np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    res_std = float(residuals.std())

    # Detect batches via host inter-arrival; re-fit on batch heads only.
    filter_src = host_ns if host_ns_for_filter is None else host_ns_for_filter
    if len(filter_src) > 100:
        ia_ms = np.diff(filter_src) / 1e6
        batch_starts = np.concatenate(([0], np.where(ia_ms > batch_filter_threshold_ms)[0] + 1))
        if 10 <= len(batch_starts) < n // 2:  # only if real batching detected
            xb = x[batch_starts]
            yb = y[batch_starts]
            slope_b, intercept_b = np.polyfit(xb, yb, 1)
            res_b = yb - (slope_b * xb + intercept_b)
            res_std_b = float(res_b.std())
            log.info("%s batch-filtered regression: %d batch heads, "
                     "slope=%.6f ns/us, residual_std=%.3f ms (vs raw %.3f ms)",
                     name, len(batch_starts), slope_b, res_std_b / 1e6, res_std / 1e6)
            # Use batch-filtered fit (cleaner) but report raw residual too.
            slope, intercept = slope_b, intercept_b
            # Keep the batch-filtered residual as the reported one - it is the
            # true sync precision (raw residual is dominated by batch jitter).
            res_std = res_std_b

    if res_std > 50e6:
        log.warning("%s: regression fallback - residual std %.2f ms > 50 ms",
                    name, res_std / 1e6)
        return RegressionResult(slope, intercept, res_std, n, False,
                                f"residual_std_{res_std/1e6:.1f}ms")

    log.info("%s regression: slope=%.6f ns/us (drift=%.1f ppm) intercept=%.3e ns "
             "residual_std=%.2f us n=%d",
             name, slope, (slope - 1000.0) / 1000.0 * 1e6, intercept,
             res_std / 1e3, n)
    return RegressionResult(slope, intercept, res_std, n, True, "ok")


# ---------- report ----------
def stream_block(name, host_recv_ns, canonical_ns, seq, reg: RegressionResult,
                 wrap_count: int, expected_dt_ms: float) -> list[str]:
    out = [f"\n[{name}]"]
    if len(host_recv_ns) < 2:
        out.append("  too few packets")
        return out
    duration_s = (host_recv_ns[-1] - host_recv_ns[0]) / 1e9
    out.append(f"  packets:        {len(host_recv_ns)}")
    out.append(f"  duration:       {duration_s:.2f} s")
    out.append(f"  avg rate:       {(len(host_recv_ns) - 1) / duration_s:.2f} pkt/s")
    out.append(f"  mcu wraps:      {wrap_count}")
    # offset relative to canonical
    offset = host_recv_ns.astype(np.int64) - canonical_ns
    out.append(f"  host - canonical (ms): "
               f"mean={offset.mean() / 1e6:+.3f} "
               f"std={offset.std() / 1e6:.3f} "
               f"min={offset.min() / 1e6:+.3f} "
               f"max={offset.max() / 1e6:+.3f}")
    out.append(f"  regression:     slope={reg.slope:.6f} ns/us, "
               f"intercept={reg.intercept_ns:.3e} ns, "
               f"residual_std={reg.residual_std_ns / 1e6:.3f} ms, "
               f"n={reg.n}, passed={reg.passed} ({reg.reason})")
    ia = np.diff(host_recv_ns) / 1e6
    out.append(f"  inter-arrival (ms): "
               f"p50={np.percentile(ia, 50):.3f} "
               f"p95={np.percentile(ia, 95):.3f} "
               f"p99={np.percentile(ia, 99):.3f} "
               f"max={ia.max():.3f} (expected ~{expected_dt_ms:.2f})")
    dseq = (np.diff(seq.astype(np.int64)) & 0xFFFF)
    gaps = int(np.sum(dseq > 1))
    out.append(f"  sequence gaps:  {gaps}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="/home/orangepi/sensor_host/data")
    ap.add_argument("--emg-glob", default="emg_*.bin")
    ap.add_argument("--imu-glob", default="imu_*.bin")
    ap.add_argument("--out-prefix", default="aligned")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("align")

    data_dir = Path(args.data_dir)
    emg_files = sorted(data_dir.glob(args.emg_glob))
    imu_files = sorted(data_dir.glob(args.imu_glob))
    log.info("EMG files: %d, IMU files: %d", len(emg_files), len(imu_files))

    out_prefix = Path(args.out_prefix)
    report_lines = [
        "=" * 60,
        " Sensor Host Alignment Report (MCU->Host linear regression)",
        "=" * 60,
    ]

    # ---- EMG ----
    emg_data = None
    if emg_files:
        parts = [p for p in (parse_emg_file(f, log) for f in emg_files) if p]
        if parts:
            emg_data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
            mcu_cont = unwrap_mcu_ts(emg_data["mcu_ts_raw"])
            wraps = int(mcu_cont[-1] // MCU_TS_MAX) if len(mcu_cont) else 0
            reg = fit_mcu_to_host(mcu_cont, emg_data["host_recv_ns"], log, "EMG")
            if reg.passed:
                canonical = reg.apply(mcu_cont)
            else:
                canonical = emg_data["host_recv_ns"].astype(np.int64)
            report_lines += stream_block(
                "EMG", emg_data["host_recv_ns"], canonical, emg_data["seq"], reg, wraps, 0.5,
            )
            np.savez_compressed(
                out_prefix.with_name(out_prefix.name + "_emg.npz"),
                samples=emg_data["samples"],
                mcu_ts_raw=emg_data["mcu_ts_raw"],
                mcu_ts_continuous_us=mcu_cont,
                host_recv_ns=emg_data["host_recv_ns"],
                canonical_ts_ns=canonical,
                seq=emg_data["seq"],
                status=emg_data["status"],
                regression_slope=np.float64(reg.slope),
                regression_intercept=np.float64(reg.intercept_ns),
                regression_residual_std_ns=np.float64(reg.residual_std_ns),
                regression_passed=np.array([reg.passed]),
            )
            log.info("saved %s_emg.npz with %d frames", out_prefix.name,
                     len(emg_data["seq"]))

    # ---- IMU ----
    imu_data = None
    if imu_files:
        parts = [p for p in (parse_imu_file(f, log) for f in imu_files) if p]
        if parts:
            imu_data = {
                "mcu_ts_raw": np.concatenate([p["mcu_ts_raw"] for p in parts]),
                "host_recv_ns": np.concatenate([p["host_recv_ns"] for p in parts]),
                "seq": np.concatenate([p["seq"] for p in parts]),
                "samples_per_pkt": np.concatenate([p["samples_per_pkt"] for p in parts]),
            }
            mcu_cont = unwrap_mcu_ts(imu_data["mcu_ts_raw"])
            wraps = int(mcu_cont[-1] // MCU_TS_MAX) if len(mcu_cont) else 0
            reg = fit_mcu_to_host(mcu_cont, imu_data["host_recv_ns"], log, "IMU")
            if reg.passed:
                canonical_pkt = reg.apply(mcu_cont)
            else:
                canonical_pkt = imu_data["host_recv_ns"].astype(np.int64)
            report_lines += stream_block(
                "IMU", imu_data["host_recv_ns"], canonical_pkt, imu_data["seq"],
                reg, wraps, 50.0,
            )
            # Per-sample timestamps: linearly interpolate within each packet.
            # Each packet's first sample == packet.mcu_ts, samples spaced 1/200s = 5000 us.
            n_pkts = len(imu_data["seq"])
            sample_dt_ns = int(1e9 / IMU_SAMPLE_RATE_HZ)
            per_sample_canonical = np.empty(n_pkts * IMU_SAMPLES_PER_PKT, dtype=np.int64)
            for i in range(n_pkts):
                base = canonical_pkt[i]
                for j in range(IMU_SAMPLES_PER_PKT):
                    per_sample_canonical[i * IMU_SAMPLES_PER_PKT + j] = base + j * sample_dt_ns
            flat_samples = imu_data["samples_per_pkt"].reshape(-1, 9)
            np.savez_compressed(
                out_prefix.with_name(out_prefix.name + "_imu.npz"),
                samples=flat_samples,
                per_sample_canonical_ts_ns=per_sample_canonical,
                mcu_ts_raw_pkt=imu_data["mcu_ts_raw"],
                mcu_ts_continuous_us_pkt=mcu_cont,
                host_recv_pkt_ns=imu_data["host_recv_ns"],
                canonical_pkt_ts_ns=canonical_pkt,
                seq=imu_data["seq"],
                regression_slope=np.float64(reg.slope),
                regression_intercept=np.float64(reg.intercept_ns),
                regression_residual_std_ns=np.float64(reg.residual_std_ns),
                regression_passed=np.array([reg.passed]),
            )
            log.info("saved %s_imu.npz with %d packets (%d samples)",
                     out_prefix.name, n_pkts, len(flat_samples))

    # Cross-stream overlap
    if emg_data is not None and imu_data is not None:
        emg_t = unwrap_mcu_ts(emg_data["mcu_ts_raw"])
        imu_t = unwrap_mcu_ts(imu_data["mcu_ts_raw"])
        report_lines.append("\n[Cross-stream]")
        t0 = max(emg_t.min(), imu_t.min())
        t1 = min(emg_t.max(), imu_t.max())
        report_lines.append(f"  overlap window (mcu_us continuous): "
                            f"{(t1 - t0) / 1e6:.2f} s")

    report = "\n".join(report_lines) + "\n"
    print(report)
    rpt_path = out_prefix.with_name(out_prefix.name + "_report.txt")
    rpt_path.write_text(report, encoding="utf-8")
    log.info("report -> %s", rpt_path)


if __name__ == "__main__":
    sys.exit(main())
