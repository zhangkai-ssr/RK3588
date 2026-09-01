# RK3588 边缘采集与处理项目

本仓库维护 Orange Pi 5 Plus / RK3588 侧的传感器接收、部署资料、硬件参考资料与验证记录。仓库根目录并列保存各类项目资料，目录不是 Git 分支。

## 项目入口

| 路径 | 内容与入口 |
| --- | --- |
| [`sensor_host/`](sensor_host/) | Orange Pi 5 Plus 上的 EMG/IMU TCP 接收与分析工具；EMG 使用端口 `3333`，IMU 使用端口 `3334`。从 [`sensor_host/README.md`](sensor_host/README.md) 开始。 |
| [`GJ/`](GJ/) | 系统安装与烧录脚本、Orange Pi 5 Plus 硬件资料、ADS1298 模块 SDK 和配套资料。 |
| [`fwer/`](fwer/) | MIPI 摄像头转接、图像传感器规格书、Orange Pi 5 Plus 摄像头接口与 Wiki 快照。 |
| [`RK3588头环WiFi扫描记录可行性确认.md`](RK3588头环WiFi扫描记录可行性确认.md) | RK3588 头环 Wi-Fi 扫描与记录方案的可行性确认。 |
| [`AGENTS.md`](AGENTS.md) | 本仓库的目录边界、设备授权、证据分层、worktree 和验证规则。 |
| [`plan.md`](plan.md) | direct 与 worktree 工作的简要记录。 |

## 开始工作

1. 先阅读 [`AGENTS.md`](AGENTS.md) 和 [`plan.md`](plan.md)，确认协作边界与当前工作记录。
2. 主机接收与数据分析从 `sensor_host/README.md` 开始。
3. 系统部署与板卡资料从 `GJ/` 开始。
4. 摄像头、MIPI 接口与传感器选型资料从 `fwer/` 开始。

## Git LFS

系统镜像、压缩包、视频、三维模型、数据集和 PDF 等大文件使用 Git LFS。首次克隆前安装 Git LFS，克隆后执行：

```powershell
git lfs install
git lfs pull
```

本地构建输出、Python 缓存、worktree 和 `sensor_host/data/` 下的新采集数据不会进入仓库。
