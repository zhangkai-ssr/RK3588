"""Clock sync / jitter / gap monitor for sensor streams.

Slave firmware uses esp_timer_get_time() = uint32 us since boot, which wraps at
~71 minutes. We track wraps and convert to a monotonically increasing 64-bit
"mcu_ts_us_continuous" value. The host->slave mapping is then estimated by
linear regression in align_streams.py.

Live monitoring in ClockSync provides:
  - Sequence gap / out-of-order / duplicate detection
  - Inter-arrival jitter (host clock)
  - Coarse offset stats (host_recv_ns - mcu_ts_ns)
  - Wrap tracking for 32-bit MCU timestamps
"""
import collections
import logging
import time
from dataclasses import dataclass

EPOCH_NS_REF = 1_700_000_000_000_000_000  # ~2023-11; current epoch in ns


def detect_ts_unit(slave_ts: int) -> tuple[str, int]:
    """Guess slave timestamp unit (used for wall-clock formats only)."""
    if slave_ts == 0:
        return ("unknown", 1)
    ratio = slave_ts / EPOCH_NS_REF
    if 0.05 <= ratio <= 5:
        return ("epoch_ns", 1)
    ratio = slave_ts / (EPOCH_NS_REF // 1_000)
    if 0.05 <= ratio <= 5:
        return ("epoch_us", 1_000)
    ratio = slave_ts / (EPOCH_NS_REF // 1_000_000)
    if 0.05 <= ratio <= 5:
        return ("epoch_ms", 1_000_000)
    return ("boot_us", 1_000)  # default: assume us-since-boot for small values


@dataclass
class StreamHealth:
    pkts: int = 0
    seq_gaps: int = 0
    duplicates: int = 0
    out_of_order: int = 0
    offset_ns_mean: float = 0.0
    offset_ns_p1: float = 0.0
    offset_ns_p99: float = 0.0
    inter_arrival_ms_p50: float = 0.0
    inter_arrival_ms_p99: float = 0.0
    drift_ns_per_sec: float = 0.0
    unit: str = "?"
    mcu_wraps: int = 0


class ClockSync:
    """Per-stream clock health tracker with 32-bit MCU timestamp wrap handling."""

    def __init__(self, name: str, logger: logging.Logger,
                 expected_period_us: float | None = None,
                 window: int = 4000,
                 report_period_s: float = 10.0,
                 mcu_ts_bits: int = 32,
                 mcu_ts_scale_ns: int = 1000,  # default: 1 us = 1000 ns
                 batch_threshold_ms: float | None = None):
        self.name = name
        self.log = logger
        self.expected_period_us = expected_period_us
        self.window = window
        self.report_period_s = report_period_s
        self.mcu_ts_bits = mcu_ts_bits
        self.mcu_ts_max = 1 << mcu_ts_bits  # 2^32 for uint32
        self.mcu_ts_scale_ns = mcu_ts_scale_ns
        self.batch_threshold_ms = batch_threshold_ms

        # Wrap tracking
        self.mcu_wraps: int = 0
        self.last_mcu_raw: int | None = None

        # Stats
        self.offsets: collections.deque[int] = collections.deque(maxlen=window)
        self.inter_arrival_ns: collections.deque[int] = collections.deque(maxlen=window)
        self.first_host_ns: int | None = None
        self.first_offset_ns: int | None = None
        self.last_host_ns: int | None = None
        self.last_seq: int | None = None

        self.pkts = 0
        self.seq_gaps = 0
        self.duplicates = 0
        self.out_of_order = 0
        self._next_report = time.monotonic() + report_period_s

    def _continuous_mcu(self, ts_raw: int) -> int:
        """Convert raw 32-bit MCU timestamp (us) to continuous 64-bit (with wraps)."""
        if self.last_mcu_raw is not None and ts_raw < self.last_mcu_raw:
            # Backward jump: either wrap or actual reorder. If gap > half range, assume wrap.
            backward = self.last_mcu_raw - ts_raw
            if backward > self.mcu_ts_max // 2:
                self.mcu_wraps += 1
                self.log.warning("%s: MCU timestamp wrap detected (wrap #%d)",
                                 self.name, self.mcu_wraps)
        self.last_mcu_raw = ts_raw
        return self.mcu_wraps * self.mcu_ts_max + ts_raw

    def observe(self, host_recv_ns: int, slave_ts_raw: int, seq: int):
        self.pkts += 1
        mcu_us = self._continuous_mcu(slave_ts_raw)
        mcu_ns = mcu_us * self.mcu_ts_scale_ns
        offset = host_recv_ns - mcu_ns
        self.offsets.append(offset)

        if self.last_host_ns is not None:
            self.inter_arrival_ns.append(host_recv_ns - self.last_host_ns)
        self.last_host_ns = host_recv_ns

        if self.first_host_ns is None:
            self.first_host_ns = host_recv_ns
            self.first_offset_ns = offset

        if self.last_seq is not None:
            expected = (self.last_seq + 1) & 0xFFFF
            if seq == self.last_seq:
                self.duplicates += 1
            elif seq == expected:
                pass
            else:
                forward = (seq - self.last_seq) & 0xFFFF
                if forward < 0x8000:
                    self.seq_gaps += 1
                else:
                    self.out_of_order += 1
        self.last_seq = seq

        now = time.monotonic()
        if now >= self._next_report:
            self._next_report = now + self.report_period_s
            self._report()

    @staticmethod
    def _pctl(d, p: float) -> float:
        if not d:
            return 0.0
        s = sorted(d)
        idx = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
        return float(s[idx])

    def _report(self):
        if not self.offsets:
            return
        off_mean = sum(self.offsets) / len(self.offsets)
        off_p1 = self._pctl(self.offsets, 0.01)
        off_p99 = self._pctl(self.offsets, 0.99)
        spread_ms = (off_p99 - off_p1) / 1e6

        ia_p50 = self._pctl(self.inter_arrival_ns, 0.50) / 1e6 if self.inter_arrival_ns else 0
        ia_p99 = self._pctl(self.inter_arrival_ns, 0.99) / 1e6 if self.inter_arrival_ns else 0

        drift = 0.0
        if (self.first_host_ns is not None and self.first_offset_ns is not None
                and self.last_host_ns and self.last_host_ns > self.first_host_ns):
            current_offset = self.offsets[-1]
            elapsed_s = (self.last_host_ns - self.first_host_ns) / 1e9
            if elapsed_s > 0:
                drift = (current_offset - self.first_offset_ns) / elapsed_s

        self.log.info(
            "%s sync: offset=%+.1fs (host-mcu_boot) spread=%.2f ms | "
            "inter-arrival p50=%.2f ms p99=%.2f ms | drift=%+.2f us/s | "
            "pkts=%d gaps=%d ooo=%d dup=%d wraps=%d",
            self.name,
            off_mean / 1e9, spread_ms,
            ia_p50, ia_p99,
            drift / 1e3,
            self.pkts, self.seq_gaps, self.out_of_order, self.duplicates, self.mcu_wraps,
        )
        # NOTE: jitter warning is suppressed when batch_threshold_ms is set,
        # because batched senders (e.g. ESP32 50-frame EMG batches) naturally
        # produce p99 ~= batch_period regardless of actual WiFi quality.
        # Use the higher of (3x expected period) or (1.5x batch_threshold_ms).
        if self.expected_period_us is not None:
            base_threshold_ms = self.expected_period_us / 1000 * 3
            if self.batch_threshold_ms is not None:
                base_threshold_ms = max(base_threshold_ms, self.batch_threshold_ms * 1.5)
            if ia_p99 > base_threshold_ms:
                self.log.warning(
                    "%s: WiFi jitter spike, p99=%.2f ms exceeds threshold %.2f ms",
                    self.name, ia_p99, base_threshold_ms,
                )

    def summary(self) -> StreamHealth:
        if not self.offsets:
            return StreamHealth(unit="boot_us", mcu_wraps=self.mcu_wraps)
        off_mean = sum(self.offsets) / len(self.offsets)
        ia_p50 = self._pctl(self.inter_arrival_ns, 0.50) / 1e6 if self.inter_arrival_ns else 0
        ia_p99 = self._pctl(self.inter_arrival_ns, 0.99) / 1e6 if self.inter_arrival_ns else 0
        drift = 0.0
        if (self.first_host_ns is not None and self.first_offset_ns is not None
                and self.last_host_ns and self.last_host_ns > self.first_host_ns):
            elapsed_s = (self.last_host_ns - self.first_host_ns) / 1e9
            if elapsed_s > 0:
                drift = (self.offsets[-1] - self.first_offset_ns) / elapsed_s
        return StreamHealth(
            pkts=self.pkts,
            seq_gaps=self.seq_gaps,
            duplicates=self.duplicates,
            out_of_order=self.out_of_order,
            offset_ns_mean=off_mean,
            offset_ns_p1=self._pctl(self.offsets, 0.01),
            offset_ns_p99=self._pctl(self.offsets, 0.99),
            inter_arrival_ms_p50=ia_p50,
            inter_arrival_ms_p99=ia_p99,
            drift_ns_per_sec=drift,
            unit="boot_us",
            mcu_wraps=self.mcu_wraps,
        )
