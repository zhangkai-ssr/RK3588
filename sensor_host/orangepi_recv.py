#!/usr/bin/env python3
"""Orange Pi 端 EMG + IMU TCP 接收 / 落盘脚本（纯标准库，Linux/Python3）。

ESP32 是 TCP 客户端，会主动连到本机（OrangePi_AP 网关 10.42.0.1）：
    :3333  EMG  ADS1298 ×2  16ch @ 2000 SPS   (帧头 0xAA / 帧尾 0x55, 64B)
    :3334  IMU  LSM9DS1TR 9轴 @ 200 Hz         (帧头 0xBB / 帧尾 0x55, 211B)

本脚本在这两个端口上 listen，accept ESP32 的连接，按字节流解析、
落盘 CSV，并周期性打印吞吐量 / 丢包 / IMU 实时样本值。

用法（在 Orange Pi 上）：
    python3 orangepi_recv.py                 # 默认监听 0.0.0.0，落盘到 ~/sensor_log
    python3 orangepi_recv.py --logdir /tmp/log
    python3 orangepi_recv.py --no-csv        # 只监控不落盘
"""

import argparse
import os
import socket
import struct
import threading
import time
from datetime import datetime

# ---- EMG 封包（必须与 ads1298_stream.c v0x02 一致）----
EMG_PORT      = 3333
EMG_HDR, EMG_VER, EMG_FTR = 0xAA, 0x02, 0x55
EMG_PKT_LEN   = 64
EMG_DEV_LEN   = 27       # 每颗 ADS1298 帧：3 状态字节 + 8ch×3
EMG_DEV_COUNT = 2
EMG_CH_PER_DEV = 8
EMG_TOTAL_CH  = 16
EMG_FS_HZ     = 2000

# ---- IMU 封包（必须与 imu_stream.c 一致）----
IMU_PORT      = 3334
IMU_HDR, IMU_VER, IMU_TYPE, IMU_FTR = 0xBB, 0x01, 0x20, 0x55
IMU_BATCH     = 10       # 每包 10 个样本
IMU_SAMPLE_BYTES = 20    # ax ay az gx gy gz mx my mz rsvd (int16 LE ×10)
IMU_PKT_LEN   = 1 + 1 + 1 + 2 + 4 + 1 + IMU_BATCH * IMU_SAMPLE_BYTES + 1  # = 211
IMU_FS_HZ     = 200


def _int24_be(b0, b1, b2):
    v = (b0 << 16) | (b1 << 8) | b2
    if v & 0x800000:
        v -= 0x1000000
    return v


def _shift_left_1bit_27(buf):
    """菊花链 dead-bit 补偿：chip B 的 27 字节整体左移 1 位。"""
    out = bytearray(27)
    for i in range(26):
        out[i] = ((buf[i] << 1) & 0xFF) | (buf[i + 1] >> 7)
    out[26] = (buf[26] << 1) & 0xFF
    return out


def seq_gap(prev, cur):
    """uint16 序号差（处理 65535→0 回绕），返回丢失的包数。"""
    if prev is None:
        return 0
    return (cur - prev - 1) & 0xFFFF


# ----------------------------------------------------------------------------
def parse_emg_record(rec, csv_fp, sample_idx):
    """解析 64 字节 EMG 记录，返回 (seq, samples_16)。可选写 CSV。"""
    seq = rec[2] | (rec[3] << 8)
    mcu_ts = rec[4] | (rec[5] << 8) | (rec[6] << 16) | (rec[7] << 24)
    chip_a = rec[9:9 + EMG_DEV_LEN]
    chip_b = _shift_left_1bit_27(rec[9 + EMG_DEV_LEN:9 + 54])
    samples = [0] * EMG_TOTAL_CH
    for d_idx, frame in enumerate((chip_a, chip_b)):
        base = d_idx * EMG_CH_PER_DEV
        for ch in range(EMG_CH_PER_DEV):
            so = 3 + ch * 3
            samples[base + ch] = _int24_be(frame[so], frame[so + 1], frame[so + 2])
    if csv_fp is not None:
        t_s = sample_idx / EMG_FS_HZ
        csv_fp.write("%d,%.6f,%d,%d,%d,%s\n" % (
            sample_idx, t_s, time.time_ns(), mcu_ts, seq,
            ",".join(str(s) for s in samples)))
    return seq, samples


def parse_imu_packet(pkt, csv_fp, sample_idx):
    """解析 211 字节 IMU 包（含 10 个样本），返回 (seq, last_sample_9)。"""
    seq = pkt[3] | (pkt[4] << 8)
    mcu_ts = pkt[5] | (pkt[6] << 8) | (pkt[7] << 16) | (pkt[8] << 24)
    n = pkt[9]
    last9 = None
    off = 10
    for i in range(n):
        ax, ay, az, gx, gy, gz, mx, my, mz, _rsvd = struct.unpack_from("<10h", pkt, off)
        off += IMU_SAMPLE_BYTES
        last9 = (ax, ay, az, gx, gy, gz, mx, my, mz)
        if csv_fp is not None:
            idx = sample_idx + i
            t_s = idx / IMU_FS_HZ
            csv_fp.write("%d,%.6f,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n" % (
                idx, t_s, time.time_ns(), mcu_ts, seq,
                ax, ay, az, gx, gy, gz, mx, my, mz))
    return seq, n, last9


# ----------------------------------------------------------------------------
def serve_emg(args):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, EMG_PORT))
    srv.listen(1)
    print("[EMG] listening on %s:%d" % (args.bind, EMG_PORT))
    while True:
        conn, addr = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print("[EMG] connected from %s:%d" % addr)
        csv_fp = None
        if not args.no_csv:
            path = os.path.join(args.logdir,
                                "emg_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
            csv_fp = open(path, "w", buffering=1 << 20)
            csv_fp.write("# EMG ADS1298x2 16ch fs=%dHz\n" % EMG_FS_HZ)
            csv_fp.write("sample_idx,t_s,host_ts_ns,mcu_ts_us,seq,%s\n"
                         % ",".join("ch%d" % c for c in range(EMG_TOTAL_CH)))
            print("[EMG] recording -> %s" % path)
        buf = bytearray()
        sample_idx = 0
        prev_seq = None
        good = bad = lost = 0
        last_report = time.time()
        last_good = 0
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                buf.extend(data)
                # 字节流解析 + 重同步
                while len(buf) >= EMG_PKT_LEN:
                    if buf[0] == EMG_HDR and buf[1] == EMG_VER and buf[EMG_PKT_LEN - 1] == EMG_FTR:
                        seq, _ = parse_emg_record(buf[:EMG_PKT_LEN], csv_fp, sample_idx)
                        sample_idx += 1
                        lost += seq_gap(prev_seq, seq)
                        prev_seq = seq
                        good += 1
                        del buf[:EMG_PKT_LEN]
                    else:
                        # 找下一个可能的帧头，丢弃前面的脏字节
                        nxt = buf.find(EMG_HDR, 1)
                        if nxt < 0:
                            bad += len(buf)
                            buf.clear()
                        else:
                            bad += nxt
                            del buf[:nxt]
                now = time.time()
                if now - last_report >= 2.0:
                    rate = (good - last_good) / (now - last_report)
                    print("[EMG] good=%d (%.0f pkt/s = %.0f sps) lost=%d bad_bytes=%d"
                          % (good, rate, rate, lost, bad))
                    last_report = now
                    last_good = good
        except (ConnectionResetError, OSError) as e:
            print("[EMG] connection error: %s" % e)
        finally:
            conn.close()
            if csv_fp:
                csv_fp.close()
            print("[EMG] disconnected. total good=%d lost=%d bad_bytes=%d" % (good, lost, bad))


def serve_imu(args):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.bind, IMU_PORT))
    srv.listen(1)
    print("[IMU] listening on %s:%d" % (args.bind, IMU_PORT))
    while True:
        conn, addr = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print("[IMU] connected from %s:%d" % addr)
        csv_fp = None
        if not args.no_csv:
            path = os.path.join(args.logdir,
                                "imu_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M%S"))
            csv_fp = open(path, "w", buffering=1 << 20)
            csv_fp.write("# IMU LSM9DS1TR 9-axis fs=%dHz\n" % IMU_FS_HZ)
            csv_fp.write("sample_idx,t_s,host_ts_ns,mcu_ts_us,seq,"
                         "ax,ay,az,gx,gy,gz,mx,my,mz\n")
            print("[IMU] recording -> %s" % path)
        buf = bytearray()
        sample_idx = 0
        prev_seq = None
        good = bad = lost = 0
        last_report = time.time()
        last_good = 0
        last9 = None
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                buf.extend(data)
                while len(buf) >= IMU_PKT_LEN:
                    if (buf[0] == IMU_HDR and buf[1] == IMU_VER and buf[2] == IMU_TYPE
                            and buf[IMU_PKT_LEN - 1] == IMU_FTR):
                        seq, n, last9 = parse_imu_packet(buf[:IMU_PKT_LEN], csv_fp, sample_idx)
                        sample_idx += n
                        lost += seq_gap(prev_seq, seq) * IMU_BATCH
                        prev_seq = seq
                        good += 1
                        del buf[:IMU_PKT_LEN]
                    else:
                        nxt = buf.find(IMU_HDR, 1)
                        if nxt < 0:
                            bad += len(buf)
                            buf.clear()
                        else:
                            bad += nxt
                            del buf[:nxt]
                now = time.time()
                if now - last_report >= 2.0:
                    rate = (good - last_good) / (now - last_report)
                    msg = ("[IMU] good=%d (%.0f pkt/s = %.0f sps) lost=%d bad_bytes=%d"
                           % (good, rate, rate * IMU_BATCH, lost, bad))
                    if last9:
                        msg += ("  | a=(%6d,%6d,%6d) g=(%6d,%6d,%6d) m=(%6d,%6d,%6d)"
                                % last9)
                    print(msg)
                    last_report = now
                    last_good = good
        except (ConnectionResetError, OSError) as e:
            print("[IMU] connection error: %s" % e)
        finally:
            conn.close()
            if csv_fp:
                csv_fp.close()
            print("[IMU] disconnected. total good=%d lost=%d bad_bytes=%d" % (good, lost, bad))


def main():
    ap = argparse.ArgumentParser(description="Orange Pi EMG+IMU TCP receiver")
    ap.add_argument("--bind", default="0.0.0.0", help="本机监听地址（默认所有网卡）")
    ap.add_argument("--logdir", default=os.path.expanduser("~/sensor_log"),
                    help="CSV 落盘目录")
    ap.add_argument("--no-csv", action="store_true", help="只监控不落盘")
    ap.add_argument("--only", choices=["emg", "imu"], help="只起其中一路")
    args = ap.parse_args()

    if not args.no_csv:
        os.makedirs(args.logdir, exist_ok=True)
        print("CSV 落盘目录: %s" % args.logdir)

    threads = []
    if args.only != "imu":
        threads.append(threading.Thread(target=serve_emg, args=(args,), daemon=True))
    if args.only != "emg":
        threads.append(threading.Thread(target=serve_imu, args=(args,), daemon=True))
    for t in threads:
        t.start()
    print("接收中… Ctrl-C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出。")


if __name__ == "__main__":
    main()
