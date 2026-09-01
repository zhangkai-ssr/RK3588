# RK3588头环 WiFi扫描与记录可行性确认

## 结论

这个 RK3588/Orange Pi 5 Plus 头环可以扫描周围 WiFi 并记录下来，但前提是机器上必须有 WiFi 网卡模块。

Orange Pi 5 Plus 板子本身没有板载 WiFi。也就是说，RK3588 主板本身不能直接扫描 WiFi，必须通过外接 PCIe WiFi 模块或 USB WiFi 网卡实现。

当前工程脚本里已经出现过 `wlP2p33s0` 无线接口，说明实际机器之前大概率已经使用过外接 WiFi 模块。如果 Orange Pi 上能看到类似 `wlan0` 或 `wlP2p33s0` 的无线接口，就可以扫描并保存周围 WiFi 信息。

## 硬件判断

可用的硬件路径：

1. M.2 E-Key PCIe WiFi6/蓝牙模块
2. USB WiFi 网卡

需要确认：

- 模块能被 Linux/Ubuntu 识别
- 驱动在当前 Orange Pi 5 Plus 镜像里可用
- 系统里能看到无线接口，例如 `wlan0` 或 `wlP2p33s0`
- 如果头环还要用 WiFi 传 EMG/IMU 数据，扫描频率不要太高，避免影响实时数据传输

## 软件实现

最简单的软件方案是不写驱动，直接用 Linux 自带的 NetworkManager 工具扫描。

确认无线网卡：

```bash
nmcli dev
ip -br a
lspci | grep -i -E 'network|wireless|wifi'
lsusb | grep -i -E 'wifi|wireless|realtek|mediatek|intel'
```

扫描周围 WiFi：

```bash
sudo nmcli dev wifi rescan
nmcli -t -f SSID,BSSID,CHAN,FREQ,SIGNAL,SECURITY dev wifi list
```

当前工程已提供保存脚本：

```bash
sensor_host/scan_wifi_log.sh
```

把 `sensor_host` 目录放到 Orange Pi 上后运行：

```bash
cd /home/orangepi/sensor_host
chmod +x scan_wifi_log.sh
./scan_wifi_log.sh wifi_scans.log 60
```

上面命令会每 60 秒扫描一次，并追加保存到 `wifi_scans.log`。

只扫描一次：

```bash
ONCE=1 ./scan_wifi_log.sh wifi_scans.log
```

如果无线接口不是默认自动选择，指定接口：

```bash
WIFI_IFACE=wlP2p33s0 ./scan_wifi_log.sh wifi_scans.log 60
```

记录内容包括：

- 时间
- SSID
- BSSID
- 信道
- 频率
- 速率
- 信号强度
- 信号条
- 加密方式

## 注意事项

普通 WiFi 扫描只能记录周围热点信息，不能记录 WiFi 密码，也不应该采集别人的网络流量内容。

如果头环正在通过 WiFi 传输 EMG/IMU 数据，建议每 30 到 60 秒扫描一次。若实时性要求高，最好使用有线网络传数据，或者增加第二个 WiFi 适配器专门负责扫描。
