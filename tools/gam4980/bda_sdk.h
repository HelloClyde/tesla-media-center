#pragma once
#include <stdint.h>
#include <stddef.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
void *memset(void *, int, size_t);
void *memcpy(void *, const void *, size_t);
#define bda_memset memset
#define bda_memcpy memcpy
