#ifndef __CIRCULAR_BUFFER_H
#define __CIRCULAR_BUFFER_H

#include "Arduino.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

class CircularBufferClass
{
  public:
    bool init(uint16_t size);          // 初始化环形缓冲区
    void buffer_free();                 // 释放环形缓冲区
    bool is_empty();                   // 检查缓冲区是否为空
    bool is_full();                    // 检查缓冲区是否已满
    uint16_t get_data_count();         // 获取当前缓冲区中的数据量
    bool write(const uint8_t *data, uint16_t len); // 写入数据
    bool read(uint8_t *data, uint16_t len);        // 读取数据

   private:
    uint8_t *buffer;      // 动态分配的缓冲区指针
    uint16_t bufferSize;  // 缓冲区大小
    volatile uint16_t head; // 头指针（写入位置）
    volatile uint16_t tail; // 尾指针（读取位置）
    volatile uint16_t dataCount; // 当前缓冲区中的数据量
};

#endif // __CIRCULAR_BUFFER_H