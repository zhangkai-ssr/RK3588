# Orange Pi 5 Plus 与 AS-AA018AB50M1-50 摄像头接线说明

## 结论

当前摄像头模组 `AS-AA018AB50M1-50` 不能直接插到 Orange Pi 5 Plus 的摄像头接口。

原因：

- Orange Pi 5 Plus 板端 `CAM` 接口是 30pin，原理图连接器型号为 `OK-10F030-04`。
- 摄像头模组 `AS-AA018AB50M1-50` 是 22pin，0.5mm FPC。
- 两边 pin 数和脚序都不同，不能用普通排线硬接。

需要做一块 `30pin -> 22pin` 的转接板或转接线。

## 已确认资料

### 摄像头模组

本地资料：

- `C:\work1\JSZN\APRK3588\fwer\AS-AA018AB50M1-50(1).pdf`
- `C:\work1\JSZN\APRK3588\fwer\OG05B10_CSP_DS_1.03.pdf`

关键信息：

- 模组型号：`AS-AA018AB50M1-50`
- Sensor：`OG05B10`
- 分辨率：`1944 x 1944`
- 接口：22pin FPC
- MIPI：2-lane CSI
- 供电：
  - `POWER 3.3V`
  - `DVDD 1.2V`
  - `DOVDD 1.8V`
  - `AVDD 2.8V`

### Orange Pi 5 Plus 板端

本地原理图：

- `C:\work1\JSZN\APRK3588\fwer\OPI5_PLUS_V11_20230519-GK_with_watermark.pdf`
- 第 34 页：`VI-Camera_MIPI_CSI-RX`

关键信息：

- 板端接口：`CAM`
- 连接器：`OK-10F030-04`
- pin 数：30pin
- 支持 MIPI CSI0，最多 4-lane

官方 Wiki：

- <http://www.orangepi.cn/orangepiwiki/index.php/Orange_Pi_5_Plus>

官方 Wiki 说明官方摄像头套件使用专用 FPC，标注 `TO MB` 的一端插开发板摄像头接口，标注 `TO CAMERA` 的一端插摄像头转接板。

## Pin 对照

| Orange Pi CAM 30pin | 摄像头 AS-AA018AB50M1-50 22pin | 说明 |
|---|---|---|
| 13/14 `VCC_3V3_S0` | 1 `POWER 3.3V` | 模组主供电 |
| 6 `I2C3_SDA_M0_MIPI` | 2 `SDA` | I2C/SCCB 数据 |
| 5 `I2C3_SCL_M0_MIPI` | 3 `SCL` | I2C/SCCB 时钟 |
| GND | 4 `GND` | 地 |
| 9 `MIPI_CSI0_PDN0_H` | 5 `GPIO0` | 需确认 GPIO0 是否为 PWDN |
| 8 `CAM_RST_L` | 6 `RESET` | 复位 |
| GND | 7 `GND` | 地 |
| NC | 8 `NC` | 不接 |
| NC | 9 `NC` | 不接 |
| GND | 10 `GND` | 地 |
| NC | 11 `NC` | 不接 |
| NC | 12 `NC` | 不接 |
| GND | 13 `GND` | 地 |
| 23 `MIPI_CSI0_RX_CLK0P` | 14 `CLK_P` | MIPI 时钟正 |
| 22 `MIPI_CSI0_RX_CLK0N` | 15 `CLK_N` | MIPI 时钟负 |
| GND | 16 `GND` | 地 |
| 20 `MIPI_CSI0_RX_D1P` | 17 `D1_P` | MIPI lane 1 正 |
| 19 `MIPI_CSI0_RX_D1N` | 18 `D1_N` | MIPI lane 1 负 |
| GND | 19 `GND` | 地 |
| 16 `MIPI_CSI0_RX_D0P` | 20 `D0_P` | MIPI lane 0 正 |
| 17 `MIPI_CSI0_RX_D0N` | 21 `D0_N` | MIPI lane 0 负 |
| GND | 22 `GND` | 地 |

Orange Pi 侧的 `D2/D3` 两组数据线不用，因为当前摄像头模组只有 2-lane。

## 风险点

1. 不能直接插

   Orange Pi 是 30pin，摄像头是 22pin，脚序不一致。

2. `GPIO0` 功能要确认

   摄像头图纸里 pin 5 是 `GPIO0`，Orange Pi 侧对应的是 `MIPI_CSI0_PDN0_H`。如果 `GPIO0` 不是 PWDN，需要厂家确认控制脚定义。

3. `MIPI_CAM_CLK` 未匹配到摄像头 22pin

   Orange Pi 原理图中 pin 11 有 `MIPI_CAM_CLK`，但 `AS-AA018AB50M1-50` 22pin 表里没有单独 `MCLK/XVCLK`。需要确认模组是否板上自带时钟，或图纸是否省略了时钟脚。

4. 驱动不等于硬件接通

   接线正确后，还需要 Linux/Android 内核有 `OG05B10` sensor 驱动和设备树配置，否则不会正常出图。

## 可买到的相关配件

### 官方摄像头套件

如果目标只是让 Orange Pi 5 Plus 跑摄像头，最省事是换官方支持的 OV13855 套件。

- Orange Pi 13MP Camera 13855：<https://www.orangepi.cn/html/hardWare/computerAndMicrocontrollers/details/13-MP-Camera-13855.html>

### 第三方 Orange Pi 5 Camera Adapter

可把 Orange Pi 5 系列摄像头口转到 Raspberry Pi 摄像头生态，但不是给当前 `AS-AA018AB50M1-50` 脚序定制的。

- Tachyn Labs Orange Pi 5 Camera Adapter：<https://tachynlabs.com/b/opi5-cam>
- eBay 同款：<https://www.ebay.com/itm/146844118184>

注意：这类转接板按 Raspberry Pi 摄像头脚序设计，不能保证适配当前 OG05B10 模组。

## 自制转接板建议

板端连接器可选：

- `OK-10GM30-04` / `OK-10F030-04`
- JLCPCB 料号页：<https://jlcpcb.com/partdetail/-OK_10GM3004/C9900137341>
- Hirose 替代：`KN13C0.7-30DP-0.4V(800)`
- DigiKey：<https://www.digikey.com/en/products/detail/hirose-electric-co-ltd/KN13C0-7-30DP-0-4V-800/11482778>

摄像头侧 22pin FPC 座：

- Molex `503480-2200`
- 官方页：<https://www.molex.com/en-us/products/part-detail/5034802200>

最小转接板只需要走：

- 3.3V
- GND
- I2C SDA/SCL
- RESET
- PWDN/GPIO0
- MIPI CLK
- MIPI D0
- MIPI D1

不用引出 Orange Pi 侧的 D2/D3。

## 推荐下一步

1. 向摄像头厂家确认 `GPIO0` 和 `MCLK/XVCLK` 定义。
2. 用万用表确认 Orange Pi CAM 连接器 pin1 方向。
3. 画一块 30pin-to-22pin 小转接板。
4. 接线前先只测供电，不插摄像头。
5. 供电确认无误后再接 MIPI/I2C/控制线。

