// File: header_def.h
// Purpose: header with a definition
// Author: test
// Date: 2026-10-21
#ifndef HEADER_DEF_H
#define HEADER_DEF_H
#include <stdint.h>
extern uint32_t header_ok_count;
uint32_t header_bad_count;                     // EXPECT KSYS-HDR-01
uint32_t Header_GetCount(void);
#endif
