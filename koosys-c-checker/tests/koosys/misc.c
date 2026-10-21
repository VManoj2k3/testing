// File: misc.c
// Purpose: KooSys type/comment/pointer/preprocessor/loop fixtures
// Author: test
// Date: 2026-10-21
#include <stdint.h>
#include "Std_Types.h"

#define MISC_SQUARE(x) ((x) * (x))             // EXPECT KSYS-PRE-01
#ifdef MISC_DEBUG                              // EXPECT KSYS-PRE-01
#define MISC_LEVEL 2U
#endif

unsigned int misc_raw_count;                   // EXPECT KSYS-TYPE-01
uint8 misc_autosar_ok;
uint8_t misc_stdint_ok;

/* a block comment */                          // EXPECT KSYS-CMT-01
/** @brief doxygen block is allowed */
Std_ReturnType Misc_Check(uint8_t value)
{
    Std_ReturnType ret = E_NOT_OK;
    if (value > 3U) {
        ret = E_OK;
    }
    return ret;
}

Std_ReturnType Misc_Raw(uint8_t value)
{
    if (value == 0U) {
        return 1;                              // EXPECT KSYS-TYPE-02
    }
    return E_OK;
}

void Misc_Pointer(void)
{
    uint8_t *p_data;                           // EXPECT KSYS-PTR-01
    uint8_t *p_ok = NULL;
    (void)p_data; (void)p_ok;
}

void Misc_Loop(void)
{
    for (;;) {                                 // EXPECT KSYS-LOOP-01
        misc_raw_count++;
    }
}
