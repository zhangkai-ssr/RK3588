#ifndef __ADS1298_H
#define __ADS1298_H

#include "main.h"

#define ADS1298_CS_PORT                ADS1298_SPI1_CS_GPIO_Port
#define ADS1298_CS_PIN                 ADS1298_SPI1_CS_Pin
#define ADS1298_START_PORT             ADS1298_START_GPIO_Port
#define ADS1298_START_PIN              ADS1298_START_Pin
#define ADS1298_PWDN_PORT              ADS1298_PWDN_GPIO_Port
#define ADS1298_PWDN_PIN               ADS1298_PWDN_Pin
#define ADS1298_DRDY_PORT              ADS1298_DRDY_GPIO_Port
#define ADS1298_DRDY_PIN               ADS1298_DRDY_Pin
#define ADS1298_REST_PORT              ADS1298_REST_GPIO_Port
#define ADS1298_REST_PIN               ADS1298_REST_Pin

#define ADS1298_CS_H			HAL_GPIO_WritePin(ADS1298_CS_PORT, ADS1298_CS_PIN,GPIO_PIN_SET)
#define ADS1298_CS_L			HAL_GPIO_WritePin(ADS1298_CS_PORT, ADS1298_CS_PIN,GPIO_PIN_RESET)
#define ADS1298_PWDN_H		HAL_GPIO_WritePin(ADS1298_PWDN_PORT, ADS1298_PWDN_PIN,GPIO_PIN_SET)
#define ADS1298_PWDN_L		HAL_GPIO_WritePin(ADS1298_PWDN_PORT, ADS1298_PWDN_PIN,GPIO_PIN_RESET)
#define ADS1298_START_H		HAL_GPIO_WritePin(ADS1298_START_PORT, ADS1298_START_PIN,GPIO_PIN_SET)
#define ADS1298_START_L		HAL_GPIO_WritePin(ADS1298_START_PORT, ADS1298_START_PIN,GPIO_PIN_RESET)
#define ADS1298_REST_H		HAL_GPIO_WritePin(ADS1298_REST_PORT, ADS1298_REST_PIN,GPIO_PIN_SET)
#define ADS1298_REST_L		HAL_GPIO_WritePin(ADS1298_REST_PORT, ADS1298_REST_PIN,GPIO_PIN_RESET)


#define LED_H		HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin,GPIO_PIN_SET)
#define LED_L		HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin,GPIO_PIN_RESET)

/*ADS1298命令定义*/
/*系统命令*/
#define ADS1298_WAKEUP	        	0X02	//从待机模式唤醒
#define ADS1298_STANDBY	        0X04	//进入待机模式
#define ADS1298_ADSRESET        	0X06	//复位
#define ADS1298_START	        	0X08	//启动或转换
#define ADS1298_STOP	        		0X0A	//停止转换
#define ADS1298_OFFSETCAL				0X1A	//通道偏移校准
/*数据读取命令*/
#define ADS1298_RDATAC	        	0X10	//启用连续的数据读取模式,默认使用此模式
#define ADS1298_SDATAC	        	0X11	//停止连续的数据读取模式
#define ADS1298_RDATA	        	0X12	//通过命令读取数据;支持多种读回。
/*寄存器读取命令*/
#define	ADS1298_RREG	        		0X20	//读取001r rrrr 000n nnnn  这里定义的只有高八位，低8位在发送命令时设置
#define ADS1298_WREG	        		0X40	//写入010r rrrr 000n nnnn

/*	r rrrr=要读、写的寄存器地址
		n nnnn=要读、写的数据		*/


/* ADS1298内部寄存器地址定义	*/
#define ADS1298_REG_ID            0x00        // ID Control Register : The ID Control Register is programmed during device manufacture to indicate device characteristics
#define ADS1298_REG_CONFIG1       0x01        // Configuration Register 1
#define ADS1298_REG_CONFIG2       0x02        // Configuration Register 2
#define ADS1298_REG_CONFIG3       0x03        // Configuration Register 3
#define ADS1298_REG_LOFF          0x04        // Lead-Off Control Register
#define ADS1298_REG_CH1SET        0x05        // The CH[1]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH2SET        0x06        // The CH[2]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH3SET        0x07        // The CH[3]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH4SET        0x08        // The CH[4]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH5SET        0x09        // The CH[5]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH6SET        0x0A        // The CH[6]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH7SET        0x0B        // The CH[7]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_CH8SET        0x0C        // The CH[8]SET Control Register configures the power mode, PGA gain, and multiplexer settings channels
#define ADS1298_REG_RLD_SENSP     0x0D        // Controls the selection of the positive signals from each channel for right leg drive derivation
#define ADS1298_REG_RLD_SENSN     0x0E        // Controls the selection of the negative signals from each channel for right leg drive derivation
#define ADS1298_REG_LOFF_SENSP    0x0F        // Selects the positive side from each channel for lead-off detection
#define ADS1298_REG_LOFF_SENSN    0x10        // Selects the negative side from each channel for lead-off detection
#define ADS1298_REG_LOFF_FLIP     0x11        // Controls the direction of the current used for lead-off derivation
#define ADS1298_REG_LOFF_STATP    0x12        // Stores the status of whether the positive electrode on each channel is on or off (Read-Only Register)
#define ADS1298_REG_LOFF_STATN    0x13        // Stores the status of whether the negative electrode on each channel is on or off (Read-Only Register)
#define ADS1298_REG_GPIO          0x14        // General-Purpose I/O Register: controls the action of the three GPIO pins
#define ADS1298_REG_PACE          0x15        // PACE Detect Register: configure the channel signal used to feed the external PACE detect circuitry
#define ADS1298_REG_RESP          0x16        // Respiration Control Register: provides the controls for the respiration circuitry
#define ADS1298_REG_CONFIG4       0x17        // Configuration Register 4: 
#define ADS1298_REG_WCT1          0x18        // Wilson Central Terminal and Augmented Lead Control Register
#define ADS1298_REG_WCT2          0x19        // Wilson Central Terminal Control Register


void ADS1298_Init(void); //初始化ADS1292R
void ADS1298_Start(); //开始采集
void ADS1298_Stop();  //停止采集
void ADS1298_ReadData(float *chx_val);//读ADS1292数据

void ADS1298_Set_Sample_Parameter(uint8_t rate_index, uint8_t pga_index, uint8_t ch_input_index);
void ADS1298_Get_Sample_Parameter(uint8_t *rate_index, uint8_t *pga_index, uint8_t *ch_input_index);

#endif

