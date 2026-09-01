//  |ADS1298模块        | Arduino Uno         | 引脚功能          |
//  |----------------- |:--------------------:|-----------------:|
//  | GND              | Gnd                  |  Gnd             |
//  | 3.3V             | +3.3V                |  Supply voltage  |
//  | DRDY             | D2                   |  Data Ready Outpt|
//  | DOUT/MISO        | D12                  |  Slave Out       |
//  | SCLK             | D13                  |  Serial Clock    |
//  | CS               | D3                   |  Chip Select     |
//  | DIN/MOSI         | D11                  |  Slave In        |
//  | START            | D4                   |  Start Input     |
//  | RESET            | D5                   |  Reset           |
//  | PWDN             | D6                   |  Reset           |

#include <Arduino.h>
#include <SPI.h>
#include "src/ads1298.h"
#include "src/circular_buffer.h"

const int ADS1298_DRDY_PIN = 2;
const int ADS1298_CS_PIN = 3;
const int ADS1298_START_PIN = 4;
const int ADS1298_REST_PIN = 5;
const int ADS1298_PWDN_PIN = 6;


// ADS1298模块
ADS1298 *ads1298 = NULL;

// 环形数组 
CircularBufferClass *circularBuffer = NULL;

// 单次读取缓存区长度
#define READ_BUFFER_LEN 192  //6个采样点  6*32 = 192个字节

// 读取环形数据缓存区
uint8_t read_buffer[READ_BUFFER_LEN];

// 串口发送缓存区
uint8_t uart_tx_buffer[255];

//开始/停止采集数据地址
#define  ARRD_SAMPLE_CONTROL  0x11 

void setup() {

  Serial.begin(1000000);
  //Serial.begin(256000);

  circularBuffer = new CircularBufferClass();
  circularBuffer->init(1000);

  ads1298 = new ADS1298();
  ads1298->DRDY_PIN = ADS1298_DRDY_PIN;
  ads1298->START_PIN = ADS1298_START_PIN;
  ads1298->PWDN_PIN = ADS1298_PWDN_PIN;
  ads1298->CS_PIN = ADS1298_CS_PIN;
  ads1298->REST_PIN = ADS1298_REST_PIN;
  ads1298->Init();
  attachInterrupt(0,ADS1298_DRDY_Interrupt,FALLING);
  ads1298->Start();
}

void loop() {

  delay(1);

  // 判断环形数据缓存长度是否达到单次数据包的长度
  if(circularBuffer->get_data_count() > READ_BUFFER_LEN)
  {
      // 从环形缓存区提取
      circularBuffer->read(read_buffer,READ_BUFFER_LEN);
      
      // 数据帧打包
      uint8_t tx_len = ack_data_pack(ARRD_SAMPLE_CONTROL,read_buffer,READ_BUFFER_LEN,uart_tx_buffer);
    
      // 串口发送数据包
      Serial.write(uart_tx_buffer, tx_len);
  }
}

/// @brief 应答数据打包
/// @param addr 应答地址
/// @param datIn  数据内容
/// @param dataOut  数据包
/// @param len 数据内容长度
uint8_t ack_data_pack(uint8_t addr, uint8_t *data_in,uint8_t data_in_len,uint8_t *data_out)
{
	data_out[0] = 0XA5;	// 帧头
	data_out[1] = 2 + data_in_len;	// 长度
	data_out[2] = addr;	// 地址
	data_out[3] = data_out[1] ^ data_out[2];  // 帧头校验
	memcpy(data_out + 4, data_in, data_in_len);	  // 数据内容
	data_out[data_in_len + 4] = 0X5A; // 帧尾
	return data_in_len + 4 + 1; //返回数据包长度
}

void ADS1298_DRDY_Interrupt(){

   static float chx_val[8];

   // 读取ADS1298数据
   ads1298->ReadData(chx_val);

   // 写入数据
   circularBuffer->write((uint8_t *)chx_val, 8*4);
}




