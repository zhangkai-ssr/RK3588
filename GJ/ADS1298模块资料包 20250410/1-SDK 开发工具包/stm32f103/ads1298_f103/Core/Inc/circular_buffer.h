#ifndef __CIRCULAR_BUFFER_H
#define __CIRCULAR_BUFFER_H

#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

// 环形缓冲区结构体
typedef struct {
    uint8_t *buffer;      // 动态分配的缓冲区指针
    uint16_t bufferSize;  // 缓冲区大小
    volatile uint16_t head; // 头指针（写入位置）
    volatile uint16_t tail; // 尾指针（读取位置）
    volatile uint16_t dataCount; // 当前缓冲区中的数据量
} CircularBuffer;

// 函数声明
bool circular_buffer_init(CircularBuffer *cb, uint16_t bufferSize); // 初始化环形缓冲区
void circular_buffer_free(CircularBuffer *cb);                     // 释放环形缓冲区
bool circular_buffer_is_empty(CircularBuffer *cb);                   // 检查缓冲区是否为空
bool circular_buffer_is_full(CircularBuffer *cb);                    // 检查缓冲区是否已满
uint16_t circular_buffer_get_data_count(CircularBuffer *cb);          // 获取当前缓冲区中的数据量
bool circular_buffer_write(CircularBuffer *cb, const uint8_t *data, uint16_t len); // 写入数据
bool circular_buffer_read(CircularBuffer *cb, uint8_t *data, uint16_t len);        // 读取数据



#endif // __CIRCULAR_BUFFER_H