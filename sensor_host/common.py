"""Shared utilities for EMG / IMU TCP servers (Orange Pi listens, slave connects in)."""
import logging
import socket
import struct
import time
from pathlib import Path

LOG_FMT = "%(asctime)s.%(msecs)03d [%(name)s] %(levelname)s %(message)s"
DATE_FMT = "%H:%M:%S"


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FMT, DATE_FMT))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes or raise ConnectionError."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed during recv")
        buf.extend(chunk)
    return bytes(buf)


def listen_server(bind_host: str, port: int, logger: logging.Logger) -> socket.socket:
    """Open a TCP listener with SO_REUSEADDR and short backlog (single slave expected).
    A 1 s accept timeout is set so callers can poll a shutdown flag."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((bind_host, port))
    srv.listen(2)
    srv.settimeout(1.0)
    logger.info("listening on %s:%d (waiting for slave to connect in)...", bind_host, port)
    return srv


def accept_slave(srv: socket.socket, logger: logging.Logger):
    """Block (up to srv.timeout) for a slave to connect.

    Returns (conn, peer) on success, or None if accept timed out (lets caller
    poll shutdown flag). Raises on real errors.
    """
    try:
        conn, peer = srv.accept()
    except socket.timeout:
        return None
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    logger.info("slave connected from %s:%d", peer[0], peer[1])
    return conn, peer


def find_header_sync(sock: socket.socket, header: int, logger: logging.Logger) -> int:
    """Read bytes one-by-one until header byte is seen. Returns count of bytes discarded."""
    discarded = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("peer closed during sync")
        if b[0] == header:
            if discarded:
                logger.warning("resynced after discarding %d bytes", discarded)
            return discarded
        discarded += 1
        if discarded and discarded % 1024 == 0:
            logger.warning("still searching header 0x%02X, dropped %d bytes",
                           header, discarded)


def ensure_dir(path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


class RateCounter:
    """Throughput counter that prints stats every `period` seconds."""

    def __init__(self, name: str, logger: logging.Logger, period: float = 5.0):
        self.name = name
        self.logger = logger
        self.period = period
        self.t0 = time.monotonic()
        self.packets = 0
        self.bytes_ = 0
        self.samples = 0
        self.gaps = 0
        self.last_seq = None

    def tick(self, n_bytes: int, n_samples: int = 1, seq=None):
        self.packets += 1
        self.bytes_ += n_bytes
        self.samples += n_samples
        if seq is not None and self.last_seq is not None:
            expected = (self.last_seq + 1) & 0xFFFF
            if seq != expected:
                self.gaps += 1
        self.last_seq = seq
        now = time.monotonic()
        elapsed = now - self.t0
        if elapsed >= self.period:
            pps = self.packets / elapsed
            sps = self.samples / elapsed
            kbps = self.bytes_ * 8 / 1000 / elapsed
            self.logger.info(
                "%s: %.1f pkt/s, %.1f sample/s, %.1f kbps, gaps=%d",
                self.name, pps, sps, kbps, self.gaps,
            )
            self.t0 = now
            self.packets = 0
            self.bytes_ = 0
            self.samples = 0
            self.gaps = 0


def parse_int24_be(b: bytes) -> int:
    """Big-endian 24-bit signed -> int. ADS1298 outputs MSB first."""
    if len(b) != 3:
        raise ValueError("int24 requires 3 bytes")
    v = (b[0] << 16) | (b[1] << 8) | b[2]
    if v & 0x800000:
        v -= 0x1000000
    return v
