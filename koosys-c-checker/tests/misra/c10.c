/* Chapter 10: essential type model. */
#include <stdint.h>
#include <stdbool.h>

void ch10(void)
{
    bool b = true;
    int32_t s = 1;
    uint8_t u8 = 1U;
    uint32_t u32 = 1U;
    char ch = 'a';
    float f = 1.0f;
    int32_t r1 = b + 1;                        // EXPECT 10.1
    char r2 = ch + f;                          // EXPECT 10.2
    uint8_t r3 = u32;                          // EXPECT 10.3
    uint32_t r4 = u32 + s;                     // EXPECT 10.4
    bool r5 = (bool)s;                         // EXPECT 10.5
    uint32_t r6 = u8 + u8;                     // EXPECT 10.6
    uint32_t r7 = (u8 + u8) * u32;             // EXPECT 10.7
    uint32_t r8 = (uint32_t)(u8 + u8);         // EXPECT 10.8
    (void)r1; (void)r2; (void)r3; (void)r4; (void)r5; (void)r6; (void)r7; (void)r8;
}
