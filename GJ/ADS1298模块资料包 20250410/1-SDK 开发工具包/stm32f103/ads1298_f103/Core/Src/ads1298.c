/**
 ****************************************************************************************************
 * @file        ADS1298.c
 * @author      润泰实验室
 * @version     V1.0
 * @date        2025-02-14
 * @brief       ADS1298驱动代码
 * @license     Copyright (c) 2020-2032, 深圳市润谊泰谊科技有限责任公司
 ****************************************************************************************************
 * @attention
 *
 * 实验平台:RT-ADS1298模块+STM32F103核心板
 * 在线视频:
 * 技术论坛:
 * 公司网址:
 * 购买地址:
 *
 ****************************************************************************************************
 */

#include "ads1298.h"
#include "spi.h"
#include "usart.h"
#include "delay.h"
#include "string.h"

#define SPI1_Handler hspi1


static uint8_t spi_tx_buf[30];
static uint8_t spi_rx_buf[30];

// ADS1298寄存器
uint8_t ADS1298_REG[26]; 

// 放大倍数
uint8_t pga = 12;


/**
 * @brief  SPI读写
 * @param  tx_data: 发送数据缓冲区指针 
 * @param  rx_data: 接收数据缓冲区指针
 * @param  len: 发送和接收的数所长度
 * @retval 无
 */
void ADS1298_SPI_RW(uint8_t *tx_data, uint8_t *rx_data,uint8_t len)
{
	HAL_SPI_TransmitReceive(&SPI1_Handler, tx_data, rx_data, len, 10);
}


/**
 * @brief  设置SPI速率
 * @retval 无
 */
void ADS1298_SPI_Rate_Set(uint32_t baudRatePrescaler) 
{
	SPI1_Handler.Init.BaudRatePrescaler = baudRatePrescaler;
	if (HAL_SPI_Init(&SPI1_Handler) != HAL_OK)
  {
    Error_Handler();
  }
}
	
/**
 * @brief  发送命令
 * @param  cmd: 命令码 
 * @retval 无
 */
void ADS1298_Send_Cmd(uint8_t cmd)
{
	ADS1298_CS_L;
	spi_tx_buf[0] = cmd;
	ADS1298_SPI_RW(spi_tx_buf,spi_rx_buf,1);
	ADS1298_CS_H;
}

/**
 * @brief  连接写入寄存器
 * @param  addr: 寄存器起始地址 
 * @param  regs: 寄存器数组指针
 * @param  len:  写入寄存器数量
 * @retval 无
 */
void ADS1298_Write_Regs(uint8_t addr,uint8_t *regs,uint8_t len)
{
   spi_tx_buf[0] = 0x40+addr;
   spi_tx_buf[1] = 0x00+len-1;
   ADS1298_CS_L;
   ADS1298_SPI_RW(spi_tx_buf,spi_rx_buf,2);
   ADS1298_SPI_RW(regs,spi_rx_buf,len);
   ADS1298_CS_H;
}

/**
 * @brief  连接读取寄存器
 * @param  addr: 寄存器起始地址 
 * @param  regs: 寄存器数组指针
 * @param  len:  读取寄存器数量
 * @retval 无
 */
void ADS1298_Read_Regs(uint8_t addr,uint8_t *regs,uint8_t len)
{
   spi_tx_buf[0] = 0x20+addr;
   spi_tx_buf[1] = 0x00+len-1;
   ADS1298_CS_L;
	 ADS1298_SPI_RW(spi_tx_buf,spi_rx_buf,2);
	 memset(spi_tx_buf,0x00,sizeof(spi_tx_buf));
	 ADS1298_SPI_RW(spi_tx_buf,regs,len);
   ADS1298_CS_H;
}

/**
 * @brief  ADS1298上电复位
 * @retval 无
 */
void ADS1298_Rest(void)
{
  ADS1298_CS_H;
  ADS1298_START_L;
	ADS1298_REST_H;

	ADS1298_PWDN_H; 
	delay_ms(300);
	ADS1298_REST_L;
	delay_ms(10);
	ADS1298_REST_H;
	delay_ms(50); 

	ADS1298_Send_Cmd(ADS1298_SDATAC); //停止连续读取
	ADS1298_Send_Cmd(ADS1298_STOP);   //停止采集
	delay_ms(10);
}

/**
 * @brief  ADS1298 初始化
 * @retval 无
 */
void ADS1298_Init(void)
{	
	//ADS1298_SPI_Rate_Set(SPI_BAUDRATEPRESCALER_128);
	
	/* 上电复位 */
  ADS1298_Rest();

	ADS1298_REG[0x00] = 0x92;   //ID
	ADS1298_REG[0x01] = 0xC6;   //CONFIG1 0xC6(0.5kSPS) 0xC5(1kSPS) 0xC4(2kSPS) 0xC3(4kSPS) 
  ADS1298_REG[0x02] = 0x10;   //CONFIG2
  ADS1298_REG[0x03] = 0xDC;  // 0xCE;   //CONFIG3   0xDC
  ADS1298_REG[0x04] = 0x00;   //LOFF
	
//  ADS1298_REG[0x05] = 0x60;   //CH1SET
//  ADS1298_REG[0x06] = 0x65;   //CH2SET
//  ADS1298_REG[0x07] = 0x65;   //CH3SET
//  ADS1298_REG[0x08] = 0x65;   //CH4SET
//  ADS1298_REG[0x09] = 0x65;   //CH5SET
//  ADS1298_REG[0x0A] = 0x65;   //CH6SET
//  ADS1298_REG[0x0B] = 0x65;   //CH7SET
//  ADS1298_REG[0x0C] = 0x65;   //CH8SET
	
	ADS1298_REG[0x05] = 0x60;   //CH1SET
  ADS1298_REG[0x06] = 0x60;   //CH2SET
  ADS1298_REG[0x07] = 0x60;   //CH3SET
  ADS1298_REG[0x08] = 0x60;   //CH4SET
  ADS1298_REG[0x09] = 0x60;   //CH5SET
  ADS1298_REG[0x0A] = 0x60;   //CH6SET
  ADS1298_REG[0x0B] = 0x60;   //CH7SET
  ADS1298_REG[0x0C] = 0x60;   //CH8SET
	
//  ADS1298_REG[0x0D] = 0xFF;   //RLD_SENSP
//  ADS1298_REG[0x0E] = 0xFF;   //RLD_SENSN
  ADS1298_REG[0x0D] = 0x00;   //RLD_SENSP
  ADS1298_REG[0x0E] = 0x00;   //RLD_SENSN
	
  ADS1298_REG[0x0F] = 0x00;   //LOFF_SENSP 关闭导联脱落检测
  ADS1298_REG[0x10] = 0x00;   //LOFF_SENSN 关闭导联脱落检测
  ADS1298_REG[0x11] = 0x00;   //LOFF_FLIP
  ADS1298_REG[0x12] = 0x00;   //LOFF_STATP
  ADS1298_REG[0x13] = 0x00;   //LOFF_STATN
  ADS1298_REG[0x14] = 0x00;   //GPIO 
  ADS1298_REG[0x15] = 0x00;   //PACE 关闭起搏信号检测缓冲器
  ADS1298_REG[0x16] = 0x00;   //RESP 关闭呼吸检测
  ADS1298_REG[0x17] = 0x00;   //CONFIG4 
  ADS1298_REG[0x18] = 0x00;   //WCT1
	ADS1298_REG[0x19] = 0x00;   //WCT2
	
	
	// 写入寄存器 
	ADS1298_Write_Regs(0x01,ADS1298_REG+1,25);
	
	// 加入延时，确保能读取寄存器成功
	delay_ms(10);
	
	// 读取寄存器
	ADS1298_Read_Regs(0x00,ADS1298_REG,26);
  
	// 打印从器件读取的寄存器值 
	for(uint8_t n=0;n<25;n++)
	{
		printf("ads1298_reg[0x%x] = 0x%x \r\n",n,ADS1298_REG[n]);
	}
	
	// 提高SPI速率传输速率
	ADS1298_SPI_Rate_Set(SPI_BAUDRATEPRESCALER_4);
	
	//ADS1298_Start();
}


// 设置采样率、PGA放大倍数、通道输入
// 采样率:
// 0x00: 500sps
// 0x01: 1000sps
// 0x02: 2000sps
// 0x03: 4000sps
// 量程:
// 0x00: ±2.4V（PGA=1）      
// 0x01: ±1.2V（PGA=2）
// 0x02: ±800mV（PGA=3）
// 0x03: ±600mV（PGA=4）
// 0x04: ±400mV（PGA=6）
// 0x05: ±300mV（PGA=8）
// 0x06: ±200mV（PGA=12）
// 通道选择:
// 0x00: 电极输入
// 0x01: 正负极内部短路
// 0x02: 测试信号
void ADS1298_Set_Sample_Parameter(uint8_t rate_index, uint8_t pga_index, uint8_t ch_input_index)
{ 
	 //采样率
	 if(rate_index <= 0x03)
	 {
		  uint8_t rate_regs[4] = {0x06,0x05,0x04,0x03};	 
		  ADS1298_REG[0x01] |= 0x80;  //设置高分辨率模式
		  ADS1298_REG[0x01] &= 0xF8;
		  ADS1298_REG[0x01] |= rate_regs[rate_index];	 
	 }
	 
   //PGA
	 if(pga_index <= 0x06)
	 {
		 	 uint8_t pga_regs[7] = {0x01,0x02,0x03,0x04,0x00,0x05,0x06};	 
			 for(uint8_t ch=0;ch<8;ch++)
			 {
					 uint8_t reg = ADS1298_REG[0x05+ch];
					 reg &= 0x8F;
					 reg |= pga_regs[pga_index]<<4;
					 ADS1298_REG[0x05+ch] = reg;
			 } 
			 
			 // 更新放大倍数
			 uint8_t pga_vals[7] = {1,2,3,4,6,8,12};	 
		   pga = pga_vals[pga_index]; 
	 }

		// 通道输入
	  if(ch_input_index <= 0x02)
		{ 
		    uint8_t ch_regs[7] = {0x00,0x01,0x05};	 
				for(uint8_t ch=0;ch<8;ch++)
				{					
						uint8_t reg = ADS1298_REG[0x05+ch];
						reg &= 0xF8;
		        reg |= ch_regs[ch_input_index];	 
						ADS1298_REG[0x05+ch] = reg;
				}
		}
	
		// 降低SPI速率，配置寄存器
		ADS1298_SPI_Rate_Set(SPI_BAUDRATEPRESCALER_64);
		delay_ms(1);
		
		//ADS1298_START_L;
		ADS1298_Send_Cmd(ADS1298_SDATAC); //停止连续读取
	  ADS1298_Send_Cmd(ADS1298_STOP);   //停止采集
	  delay_ms(1);
		
		// 写入寄存器 
		ADS1298_Write_Regs(0x01,ADS1298_REG+1,25);
		
		// 加入延时，确保能读取寄存器成功
		delay_ms(1);
		
		// 读取寄存器
		ADS1298_Read_Regs(0x00,ADS1298_REG,26);
		
		// 打印从器件读取的寄存器值 
		for(uint8_t n=0;n<25;n++)
		{
			printf("ads1298_reg[0x%x] = 0x%x \r\n",n,ADS1298_REG[n]);
		}
		
		// 提高SPI速率，读取数据
    ADS1298_SPI_Rate_Set(SPI_BAUDRATEPRESCALER_4);
}

void ADS1298_Get_Sample_Parameter(uint8_t *rate_index, uint8_t *pga_index, uint8_t *ch_input_index)
{
	uint8_t rate_regs[4] = {0x06,0x05,0x04,0x03};
  uint8_t rate_reg = ADS1298_REG[0x01]&0x07;

	for(uint8_t i =0;i<4;i++) 
	{
		if(rate_reg == rate_regs[i])
		{
			*rate_index =  i;
			break;
		}
	}
	
	uint8_t pga_regs[7] = {0x01,0x02,0x03,0x04,0x00,0x05,0x06};	
	uint8_t pga_reg = ((ADS1298_REG[0x05] & 0x70) >> 4) & 0x07;
	for(uint8_t i =0;i<4;i++) 
	{
		if(pga_reg == pga_regs[i])
		{
			*pga_index =  i;
			break;
		}
	}
	
	uint8_t ch_regs[7] = {0x00,0x01,0x05};	 
	uint8_t ch_reg =ADS1298_REG[0x05] & 0x07;
	for(uint8_t i =0;i<4;i++) 
	{
		if(ch_reg == ch_regs[i])
		{
			*ch_input_index =  i;
			break;
		}
	}
}


/**
 * @brief  停止采集
 * @retval 无
 */
void ADS1298_Stop()
{  
	  ADS1298_Send_Cmd(ADS1298_SDATAC); //停止连续读取
    ADS1298_START_L;
	  ADS1298_CS_H;
}

/**
 * @brief  开始采集
 * @retval 无
 */
void ADS1298_Start()
{
	  memset(spi_tx_buf,0x00,sizeof(spi_tx_buf));
	  ADS1298_Send_Cmd(ADS1298_RDATAC); //开启连续读取
    ADS1298_START_H;
	  ADS1298_CS_L;
}

/**
 * @brief  开始采集
 * @retval 无
 */
void ADS1298_ReadData(float *chx_val)
{

	//ADS1298_CS_L;
	HAL_SPI_TransmitReceive(&SPI1_Handler, spi_tx_buf, spi_rx_buf, 27, 100);
	//ADS1298_CS_H;
	
	for(uint8_t ch =0;ch<8;ch++)
	{
		 uint8_t index = 3 + 3*ch;
	   chx_val[ch] = ((int32_t)(spi_rx_buf[index]<<24 | spi_rx_buf[index+1]<<16 | spi_rx_buf[index+2]<<8))/256.0f;
		
		 /* ((2*2.42)/2^24)*10^6  = 0.288486 */
		 chx_val[ch] = (chx_val[ch] * 0.288486f)/(float)pga;  //单位uV  
	}
}



