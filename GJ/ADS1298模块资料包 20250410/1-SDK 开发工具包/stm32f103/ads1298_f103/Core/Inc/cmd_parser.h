#ifndef __dat_unpack_h
#define __dat_unpack_h

#include "stdint.h"

#define CMD_FRAME_HEAFER        0xAA
#define CMD_FRAME_END           0xBB

#define DATA_FRAME_HEAFER       0xA5
#define DATA_FRAME_END          0x5A

enum
{
	  ADRR_CONN_STATUS_UPDATE =  0x09, // 连接状态更新
	  ADRR_SMAPLE_PAR        = 0x10,//采样参数配置
    ADRR_SAMPLE_CONTROL    = 0x11,//开始/停止采集数据
};//指令地址

typedef  struct
{  
	  uint8_t addr;//地址
    uint8_t isWrite; //读写指令
    uint8_t data[32];//指令内容
	  uint8_t len;   //指令内容长度
	  uint8_t ack_data[255];
} CmdData_t; //指令结构


void order_data_parse(uint8_t *buffer, uint16_t len);
uint16_t ack_data_pack(uint8_t addr, uint8_t *data_in,uint8_t data_in_len,uint8_t *data_out);

#endif

