#include "cmd_parser.h"
#include "usart.h"
#include "string.h"
#include "ads1298.h"

// 采集状态
uint8_t g_sample_status = 0;

// 连接状态
uint8_t g_conn_status = 0;

/**
 * @brief  应答数据打包
 * @param  addr: 应答地址 
 * @param  regs: 数据内容
 * @param  len:  数据内容长度
 * @retval 返回数据包长度
 */
uint16_t ack_data_pack(uint8_t addr, uint8_t *data_in,uint8_t data_in_len,uint8_t *data_out)
{
	data_out[0] = 0XA5;					  // 帧头
	data_out[1] = 2 + data_in_len;				// 长度
	data_out[2] = addr;					  // 地址
	data_out[3] = data_out[1] ^ data_out[2]; // 帧头校验
	memcpy(data_out + 4, data_in, data_in_len);	  // 数据内容
	data_out[data_in_len + 4] = 0X5A;			  // 帧尾
	return data_in_len + 4 + 1;
}

/**
 * @brief  连接状态更新回调函数
 * @param  p: 指令结构
 * @retval 元
 */
void order_conn_status_update_callback(CmdData_t *p)
{
	//printf("order_conn_status_update_callback\r\n");
	
	if (p->isWrite == 0x80)
	{
		g_conn_status = p->data[0];
    //printf("g_conn_status = %d \r\n", g_conn_status);
	}
	
	uint8_t tx_len = ack_data_pack(p->addr,(uint8_t *)&g_conn_status,1,p->ack_data);
	
	// 串口发送数据包
	HAL_UART_Transmit(&huart3, p->ack_data, tx_len, 0xffff);	 
}

// 采样参数配置
void order_sample_parameter_callBack(CmdData_t *p)
{
	if (p->isWrite== 0x80)
	{
		if (p->data[0] > 0x03 || p->data[1] > 0x06 || p->data[2] > 0x02)
		{
			return;
		}
		
    uint8_t rate_index = p->data[0];
		uint8_t pga_index = p->data[1];
		uint8_t ch_input_index = p->data[2];
    ADS1298_Set_Sample_Parameter(rate_index,pga_index,ch_input_index);
	}

	ADS1298_Get_Sample_Parameter(p->data,p->data+1,p->data+2);
  uint16_t tx_len = ack_data_pack(p->addr, p->data,3, p->ack_data);	
	HAL_UART_Transmit(&huart3, p->ack_data, tx_len, 0xffff);	 
}


/**
 * @brief  开始采集指令回调函数
 * @param  p: 指令结构
 * @retval 元
 */
void order_sample_control_callback(CmdData_t *p)
{
	printf("order_sample_control_callback\r\n");
	
	if (p->isWrite == 0x80)
	{
		uint8_t sample_status = p->data[0] == 0x00 ? 0 : 1;
		if (sample_status)
		{
	      ADS1298_Start();
		}
		else
		{
			 ADS1298_Stop();
		}		
		
		g_sample_status = sample_status;
    printf("sample_status = %d\r\n", sample_status);
	}
}


/**
 * @brief  指令帧解析
 * @param  addr: 指令地址 
 * @param  isWrite: 读写标志位
 * @param  data: 指令内容
 * @param  len: 指令内容长度
 * @retval 无
 */
void order_frame_parse(uint16_t addr, uint8_t isWrite, uint8_t *data,uint8_t len)
{
	static CmdData_t cmdData;
	cmdData.len = len;
	cmdData.isWrite = isWrite;
	cmdData.addr = addr;
	if (len > 0)
	{
		 memcpy(cmdData.data, data, len);
	}

	//printf("len:%d isWrite:0x%02x addr:0x%02x  \n ", len, isWrite, addr);
	
	switch(addr)
	{
		case ADRR_CONN_STATUS_UPDATE: order_conn_status_update_callback(&cmdData);break;
		case ADRR_SMAPLE_PAR: order_sample_parameter_callBack(&cmdData);break;
		case ADRR_SAMPLE_CONTROL: order_sample_control_callback(&cmdData);break;
	}
}

/**
 * @brief  指令数据包解析
 * @param  buffer: 指令数据指针 
 * @param  len: 指令数据长度
 * @retval 无
 */
void order_data_parse(uint8_t *buffer, uint16_t len)
{
	uint8_t *pbuf = NULL;
	uint8_t *data_out;
	do
	{
		/* 查询帧头位置 */
		pbuf = memchr(buffer, CMD_FRAME_HEAFER, len); 
		if (pbuf != NULL)
		{	
			/* 整帧长度 */
			uint8_t frameLen = pbuf[1] + 3;
			
			/* 帧长度判断 */
			if (frameLen >= 6)
			{
				/* 帧尾判断 */
				if (pbuf[frameLen - 1] == CMD_FRAME_END) 
				{
					//帧校验
					if (1)
					{	
						order_frame_parse(pbuf[3],pbuf[2],pbuf+4,frameLen-6);
						//printf("frame ok\r\n");
						buffer = pbuf + frameLen;
					}
					else
					{
						buffer = pbuf + 1;
						printf("frame check error \r\n");
					}
				}
				else
				{
				   buffer = pbuf + 1;
					 printf("frame end error \r\n");
				}
			}
			else
			{
				pbuf = NULL;
				printf("frame header error \r\n");
			}
		}
	} while (pbuf != NULL);
}
