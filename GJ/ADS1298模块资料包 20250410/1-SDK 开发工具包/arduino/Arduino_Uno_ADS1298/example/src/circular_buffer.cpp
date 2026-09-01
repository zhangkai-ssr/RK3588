#include "circular_buffer.h"

/**
 * @brief 初始化环形缓冲区
 * @param cb: 环形缓冲区结构体指针
 * @param bufferSize: 缓冲区大小
 * @return true: 初始化成功; false: 初始化失败
 */
bool CircularBufferClass::init(uint16_t size) {
    
	  // 动态分配缓冲区内存
    buffer = (uint8_t *)malloc(size);
    if (buffer == NULL) {
        return false; // 内存分配失败
    }

    // 初始化其他成员
    bufferSize = size;
    head = 0;
    tail = 0;
    dataCount = 0;

    return true;
}

/**
 * @brief 释放环形缓冲区
 * @param cb: 环形缓冲区结构体指针
 */
void CircularBufferClass::buffer_free() {
    if (buffer != NULL) {
        free(buffer); // 释放动态分配的内存
        buffer = NULL;
    }
    bufferSize = 0;
    head = 0;
    tail = 0;
    dataCount = 0;
}

/**
 * @brief 检查缓冲区是否为空
 * @param cb: 环形缓冲区结构体指针
 * @return true: 缓冲区为空; false: 缓冲区不为空
 */
bool CircularBufferClass::is_empty() {
    return dataCount == 0;
}

/**
 * @brief 检查缓冲区是否已满
 * @param cb: 环形缓冲区结构体指针
 * @return true: 缓冲区已满; false: 缓冲区未满
 */
bool CircularBufferClass::is_full() {
    return dataCount == bufferSize;
}

/**
 * @brief 获取当前缓冲区中的数据量
 * @param cb: 环形缓冲区结构体指针
 * @return 当前缓冲区中的数据量
 */
uint16_t CircularBufferClass::get_data_count() {
    return dataCount;
}

/**
 * @brief 写入数据到环形缓冲区
 * @param cb: 环形缓冲区结构体指针
 * @param data: 要写入的数据指针
 * @param len: 要写入的数据长度
 * @return true: 写入成功; false: 写入失败（缓冲区空间不足）
 */
bool CircularBufferClass::write(const uint8_t *data, uint16_t len) {
 
    if (len > bufferSize - dataCount) {
        return false; // 数据块太大，无法写入
    }

    // 锁定写位置
	uint16_t _head = head;

    // 计算从 head 到缓冲区末尾的可用空间
    uint16_t spaceToEnd = bufferSize - _head;

    if (len <= spaceToEnd) {
        // 如果数据块可以一次性写入
        memcpy(&buffer[_head], data, len);
    } else {
        // 如果数据块需要分两次写入（跨越缓冲区末尾）
        memcpy(&buffer[_head], data, spaceToEnd);
        memcpy(&buffer[0], data + spaceToEnd, len - spaceToEnd);
    }

    // 更新 head 指针和数据量
    head = (_head + len) % bufferSize;
    dataCount += len;

    return true;
}

/**
 * @brief 从环形缓冲区读取数据
 * @param cb: 环形缓冲区结构体指针
 * @param data: 存储读取数据的指针
 * @param len: 要读取的数据长度
 * @return true: 读取成功; false: 读取失败（缓冲区数据不足）
 */
bool CircularBufferClass::read(uint8_t *data, uint16_t len) {
    if (len > dataCount) {
        return false; // 数据块太大，无法读取
    }
		
		// 锁定读位置
		uint16_t _tail = tail;
		
    // 计算从 tail 到缓冲区末尾的可用数据
    uint16_t dataToEnd = bufferSize - _tail;

    if (len <= dataToEnd) {
        // 如果数据块可以一次性读取
        memcpy(data, &buffer[_tail], len);
    } else {
        // 如果数据块需要分两次读取（跨越缓冲区末尾）
        memcpy(data, &buffer[_tail], dataToEnd);
        memcpy(data + dataToEnd, &buffer[0], len - dataToEnd);
    }

    // 更新 tail 指针和数据量
    tail = (_tail + len) % bufferSize;
    dataCount -= len;

    return true;
}