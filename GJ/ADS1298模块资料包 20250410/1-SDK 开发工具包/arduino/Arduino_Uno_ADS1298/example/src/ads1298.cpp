#include "Arduino.h"
#include "ads1298.h"

static uint8_t spi_tx_buf[27];
static uint8_t spi_rx_buf[27];

/**
 * @brief  SPI读写
 * @param  tx_data: 发送数据缓冲区指针
 * @param  rx_data: 接收数据缓冲区指针
 * @param  len: 发送和接收的数所长度
 * @retval 无
 */
void ADS1298::SPIReadWrite(uint8_t *tx_data, uint8_t *rx_data, uint8_t len)
{
  for (int i = 0; i < len; i++)
  {
    rx_data[i] = SPI.transfer(tx_data[i]);
  }
}

/**
 * @brief  发送命令
 * @param  cmd: 命令码
 * @retval 无
 */
void ADS1298::SendCmd(uint8_t cmd)
{
  digitalWrite(CS_PIN, LOW);
  spi_tx_buf[0] = cmd;
  SPIReadWrite(spi_tx_buf, spi_rx_buf, 1);
  digitalWrite(CS_PIN, HIGH);
}

/**
 * @brief  连接写入寄存器
 * @param  addr: 寄存器起始地址
 * @param  regs: 寄存器数组指针
 * @param  len:  写入寄存器数量
 * @retval 无
 */
void ADS1298::WriteRegs(uint8_t addr, uint8_t *regs, uint8_t len)
{
  spi_tx_buf[0] = 0x40 + addr;
  spi_tx_buf[1] = 0x00 + len - 1;
  digitalWrite(CS_PIN, LOW);
  SPIReadWrite(spi_tx_buf, spi_rx_buf, 2);
  SPIReadWrite(regs, spi_rx_buf, len);
  digitalWrite(CS_PIN, HIGH);
}

/**
 * @brief  连接读取寄存器
 * @param  addr: 寄存器起始地址
 * @param  regs: 寄存器数组指针
 * @param  len:  读取寄存器数量
 * @retval 无
 */
void ADS1298::ReadRegs(uint8_t addr, uint8_t *regs, uint8_t len)
{
  spi_tx_buf[0] = 0x20 + addr;
  spi_tx_buf[1] = 0x00 + len - 1;
  digitalWrite(CS_PIN, LOW);
  SPIReadWrite(spi_tx_buf, spi_rx_buf, 2);
  memset(spi_tx_buf, 0x00, sizeof(spi_tx_buf));
  SPIReadWrite(spi_tx_buf, regs, len);
  digitalWrite(CS_PIN, HIGH);
}

/**
 * @brief  ADS1298上电复位
 * @retval 无
 */
void ADS1298::Rest(void)
{
  digitalWrite(REST_PIN, HIGH);
  digitalWrite(CS_PIN, HIGH);
  digitalWrite(START_PIN, LOW);

  digitalWrite(PWDN_PIN, LOW); // 进入掉电模式
  delay(50);                   // 等待稳定
  digitalWrite(PWDN_PIN, HIGH);// 退出掉电模式        
  delay(10); // 等待稳定，可以开始使用ADS1298

  SendCmd(ADS1298_SDATAC); // 停止连续读取
  SendCmd(ADS1298_STOP);   // 停止采集
}

void ADS1298::Init()
{
  // start the SPI library:
  SPI.begin();

  SPI.setBitOrder(MSBFIRST);
  // CPOL = 0, CPHA = 1
  SPI.setDataMode(SPI_MODE1);

  // Selecting 1Mhz clock for SPI
  // SPI.setClockDivider(SPI_CLOCK_DIV16);

  // Selecting 500Khz clock for SPI
  SPI.setClockDivider(SPI_CLOCK_DIV32);

  pinMode(DRDY_PIN, INPUT);
  pinMode(CS_PIN, OUTPUT);
  pinMode(START_PIN, OUTPUT);
  pinMode(PWDN_PIN, OUTPUT);
  pinMode(REST_PIN, OUTPUT);

  // attachInterrupt(0,DRDY_Interrupt,FALLING);

  // 上电复位
  Rest();

  // 寄存器配置
  ADS1298_REG[0x00] = 0xD2; // ID
  ADS1298_REG[0x01] = 0xC6; // CONFIG1 0xC6(0.5kSPS) 0xC5(1kSPS) 0xC4(2kSPS) 0xC3(4kSPS)
  ADS1298_REG[0x02] = 0x10; // CONFIG2
  ADS1298_REG[0x03] = 0xDC; // 0xCE;   //CONFIG3   0xDC
  ADS1298_REG[0x04] = 0x00; // LOFF

  // ADS1298_REG[0x05] = 0x65; // CH1SET
  // ADS1298_REG[0x06] = 0x65; // CH2SET
  // ADS1298_REG[0x07] = 0x65; // CH3SET
  // ADS1298_REG[0x08] = 0x65; // CH4SET
  // ADS1298_REG[0x09] = 0x65; // CH5SET
  // ADS1298_REG[0x0A] = 0x65; // CH6SET
  // ADS1298_REG[0x0B] = 0x65; // CH7SET
  // ADS1298_REG[0x0C] = 0x65; // CH8SET

  ADS1298_REG[0x05] = 0x60;   //CH1SET
  ADS1298_REG[0x06] = 0x60;   //CH2SET
  ADS1298_REG[0x07] = 0x60;   //CH3SET
  ADS1298_REG[0x08] = 0x60;   //CH4SET
  ADS1298_REG[0x09] = 0x60;   //CH5SET
  ADS1298_REG[0x0A] = 0x60;   //CH6SET
  ADS1298_REG[0x0B] = 0x60;   //CH7SET
  ADS1298_REG[0x0C] = 0x60;   //CH8SET

  ADS1298_REG[0x0D] = 0xFF; // RLD_SENSP
  ADS1298_REG[0x0E] = 0xFF; // RLD_SENSN
  ADS1298_REG[0x0F] = 0x00; // LOFF_SENSP 关闭导联脱落检测
  ADS1298_REG[0x10] = 0x00; // LOFF_SENSN 关闭导联脱落检测
  ADS1298_REG[0x11] = 0x00; // LOFF_FLIP
  ADS1298_REG[0x12] = 0x00; // LOFF_STATP
  ADS1298_REG[0x13] = 0x00; // LOFF_STATN
  ADS1298_REG[0x14] = 0x00; // GPIO
  ADS1298_REG[0x15] = 0x00; // PACE 关闭起搏信号检测缓冲器
  ADS1298_REG[0x16] = 0x00; // RESP 关闭呼吸检测
  ADS1298_REG[0x17] = 0x00; // CONFIG4
  ADS1298_REG[0x18] = 0x00; // WCT1
  ADS1298_REG[0x19] = 0x00; // WCT2

  // 写入寄存器
  WriteRegs(0x01, ADS1298_REG + 1, 25);
  
  delay(10);

  // 读取寄存器
  ReadRegs(0x00, ADS1298_REG, 26);

  // 打印从器件读取的寄存器值
  for (uint8_t n = 0; n < 26; n++)
  {
    Serial.print("0x");
    Serial.print(ADS1298_REG[n], HEX);
    Serial.print("\n");
  }

  // 提高SPI速率传输速率
  //Selecting 8Mhz clock for SPI
  SPI.setClockDivider(SPI_CLOCK_DIV2);
}

/**
 * @brief  停止采集
 * @retval 无
 */
void ADS1298::Stop()
{
  digitalWrite(START_PIN, LOW);
  digitalWrite(CS_PIN, HIGH);
}

/**
 * @brief  开始采集
 * @retval 无
 */
void ADS1298::Start()
{
  SendCmd(ADS1298_RDATAC); // 开启连续读取
  digitalWrite(START_PIN, HIGH);
  digitalWrite(CS_PIN, LOW);
}

/**
 * @brief  读取ADC1292转化数据
 * @param  chx_val: 两通道数据指针，float类型，单位uV
 * @retval 无
 */
void ADS1298::ReadData(float *chx_val)
{
  // 读取ADC1292转化数据
  for (int i = 0; i < 27; i++)
  {
    spi_rx_buf[i] = SPI.transfer(0x00);
  }

  uint8_t pag = 12; // 需与寄存器配置一致

  for (uint8_t ch = 0; ch < 8; ch++)
  {
    uint8_t index = 3 + 3 * ch;

    chx_val[ch] = (((int32_t)spi_rx_buf[index] << 24) | ((int32_t)spi_rx_buf[index+1] << 16) | ((int32_t)spi_rx_buf[index+2] << 8)) / 256.0f;

    /* ((2*2.42)/2^24)*10^6  = 0.288486 */
    chx_val[ch] = (chx_val[ch] * 0.288486f) / pag; // 单位uV
  }

}
