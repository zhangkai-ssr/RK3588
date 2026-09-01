#!/bin/bash
echo '=== Python ==='
python3 --version
pip3 --version 2>&1 | head -1
echo
echo '=== 网络接口 ==='
ip -br a
echo
echo '=== WiFi 信息（频段/信号） ==='
iw dev wlP2p33s0 link 2>&1 | grep -E 'freq|signal|SSID|tx bitrate|rx bitrate'
echo
echo '=== 端口 3333/3334 监听状态 ==='
ss -tlnp 2>&1 | grep -E '3333|3334' || echo '(无监听)'
echo
echo '=== 工具检查 ==='
for t in git gcc make cmake python3 pip3 nc tcpdump iperf3 numpy; do
    if command -v $t >/dev/null 2>&1; then
        echo "$t: $(command -v $t)"
    else
        echo "$t: 未安装"
    fi
done
echo
echo '=== Python 关键包 ==='
python3 -c "import numpy; print('numpy:', numpy.__version__)" 2>&1
python3 -c "import scipy; print('scipy:', scipy.__version__)" 2>&1
python3 -c "import matplotlib; print('matplotlib:', matplotlib.__version__)" 2>&1
echo
echo '=== 时区/时间 ==='
date
timedatectl 2>&1 | grep -E 'Time zone|System clock'
echo
echo '=== 磁盘/内存 ==='
df -h / | tail -1
free -h | head -2
echo
echo '=== CPU ==='
lscpu | grep -E 'Model name|CPU\(s\):|Architecture' | head -5
