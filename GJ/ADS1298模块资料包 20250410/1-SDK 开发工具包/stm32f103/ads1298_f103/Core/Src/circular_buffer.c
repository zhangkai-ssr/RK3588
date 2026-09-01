#include "circular_buffer.h"

/**
 * @brief 初始化环形缓冲区
 * @param cb: 环形缓冲区结构体指针
 * @param bufferSize: 缓冲区大小
 * @return true: 初始化成功; false: 初始化失败
 */
bool circular_buffer_init(CircularBuffer *cb, uint16_t bufferSize) {
    
	  // 动态分配缓冲区内存
    cb->buffer = (uint8_t *)malloc(bufferSize);
    if (cb->buffer == NULL) {
        return false; // 内存分配失败
    }

    // 初始化其他成员
    cb->bufferSize = bufferSize;
    cb->head = 0;
    cb->tail = 0;
    cb->dataCount = 0;

    return true;
}

/**
 * @brief 释放环形缓冲区
 * @param cb: 环形缓冲区结构体指针
 */
void circular_buffer_free(CircularBuffer *cb) {
    if (cb->buffer != NULL) {
        free(cb->buffer); // 释放动态分配的内存
        cb->buffer = NULL;
    }
    cb->bufferSize = 0;
    cb->head = 0;
    cb->tail = 0;
    cb->dataCount = 0;
}

/**
 * @brief 检查缓冲区是否为空
 * @param cb: 环形缓冲区结构体指针
 * @return true: 缓冲区为空; false: 缓冲区不为空
 */
bool circular_buffer_is_empty(CircularBuffer *cb) {
    return cb->dataCount == 0;
}

/**
 * @brief 检查缓冲区是否已满
 * @param cb: 环形缓冲区结构体指针
 * @return true: 缓冲区已满; false: 缓冲区未满
 */
bool circular_buffer_is_full(CircularBuffer *cb) {
    return cb->dataCount == cb->bufferSize;
}

/**
 * @brief 获取当前缓冲区中的数据量
 * @param cb: 环形缓冲区结构体指针
 * @return 当前缓冲区中的数据量
 */
uint16_t circular_buffer_get_data_count(CircularBuffer *cb) {
    return cb->dataCount;
}

/**
 * @brief 写入数据到环形缓冲区
 * @param cb: 环形缓冲区结构体指针
 * @param data: 要写入的数据指针
 * @param len: 要写入的数据长度
 * @return true: 写入成功; false: 写入失败（缓冲区空间不足）
 */
bool circular_buffer_write(CircularBuffer *cb, const uint8_t *data, uint16_t len) {
    if (len > cb->bufferSize - cb->dataCount) {
        return false; // 数据块太大，无法写入
    }
		
		// 锁定写位置
		uint16_t head = cb->head;

    // 计算从 head 到缓冲区末尾的可用空间
    uint16_t spaceToEnd = cb->bufferSize - head;

    if (len <= spaceToEnd) {
        // 如果数据块可以一次性写入
        memcpy(&cb->buffer[head], data, len);
    } else {
        // 如果数据块需要分两次写入（跨越缓冲区末尾）
        memcpy(&cb->buffer[head], data, spaceToEnd);
        memcpy(&cb->buffer[0], data + spaceToEnd, len - spaceToEnd);
    }

    // 更新 head 指针和数据量
    cb->head = (head + len) % cb->bufferSize;
    cb->dataCount += len;

    return true;
}

/**
 * @brief 从环形缓冲区读取数据
 * @param cb: 环形缓冲区结构体指针
 * @param data: 存储读取数据的指针
 * @param len: 要读取的数据长度
 * @return true: 读取成功; false: 读取失败（缓冲区数据不足）
 */
bool circular_buffer_read(CircularBuffer *cb, uint8_t *data, uint16_t len) {
    if (len > cb->dataCount) {
        return false; // 数据块太大，无法读取
    }
		
		// 锁定读位置
		uint16_t tail = cb->tail;
		
    // 计算从 tail 到缓冲区末尾的可用数据
    uint16_t dataToEnd = cb->bufferSize - tail;

    if (len <= dataToEnd) {
        // 如果数据块可以一次性读取
        memcpy(data, &cb->buffer[tail], len);
    } else {
        // 如果数据块需要分两次读取（跨越缓冲区末尾）
        memcpy(data, &cb->buffer[tail], dataToEnd);
        memcpy(data + dataToEnd, &cb->buffer[0], len - dataToEnd);
    }

    // 更新 tail 指针和数据量
    cb->tail = (tail + len) % cb->bufferSize;
    cb->dataCount -= len;

    return true;
}