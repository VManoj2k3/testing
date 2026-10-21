// Datei: regressions.c                        NOEXPECT KSYS-DOC-01
// Zweck: false alarms that were fixed; each NOEXPECT line must stay clean
// Autor: KooSys
// Datum: 2026-10-21
#include <stdint.h>

typedef struct
{
    unsigned int flag_a : 1;                   // NOEXPECT KSYS-TYPE-01
    unsigned int mode_b : 3;                   // NOEXPECT KSYS-TYPE-01
    uint8_t value;
} regressions_bits_t;

uint32_t string_utils_count = 0U;              // NOEXPECT KSYS-NAME-08
uint32_t memory_pool_size = 0U;                // NOEXPECT KSYS-NAME-08
uint32_t strcount;                             // EXPECT KSYS-NAME-08

#define REG_BASE 4U
enum reg_e { REG_A = 1, REG_B = REG_A + reg_base, REG_C }; // NOEXPECT KSYS-NAME-04
enum reg2_e { REG2_A = 1, reg2_b };            // EXPECT KSYS-NAME-04
