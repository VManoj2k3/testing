// File: naming.c
// Purpose: KooSys naming-rule fixtures
// Author: test
// Date: 2026-10-21
#include <stdint.h>

#define maxSpeed 100U                          // EXPECT KSYS-NAME-04
#define MAX_SPEED 100U

typedef uint8_t MyByte;                        // EXPECT KSYS-NAME-05
typedef uint8_t my_byte_t;

enum colour_e { Red, GREEN };                  // EXPECT KSYS-NAME-04

uint32_t speed;                                // EXPECT KSYS-NAME-03
uint32_t naming_speed;

static uint32_t counter;                       // EXPECT KSYS-NAME-07
static uint32_t l_counter;

static uint32_t _hidden_value;                 // EXPECT KSYS-NAME-08 EXPECT KSYS-NAME-07

uint32_t naming_a_very_long_identifier_name_x; // EXPECT KSYS-NAME-06

uint32_t computeSpeed(void)                    // EXPECT KSYS-NAME-02
{
    uint32_t result = naming_speed;
    return result;
}

uint32_t Naming_ComputeTotal(uint32_t first_value)
{
    uint32_t totalValue = first_value;         // EXPECT KSYS-NAME-01
    uint32_t total_value = totalValue + l_counter + counter;
    return total_value;
}

int main(void)
{
    return (int)Naming_ComputeTotal(computeSpeed());
}
