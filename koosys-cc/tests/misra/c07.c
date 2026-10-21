/* Chapter 7: literals and constants. */
#include <stdint.h>

void ch07(void)
{
    uint32_t a = 052;                          // EXPECT 7.1
    uint32_t b = 0x80000000;                   // EXPECT 7.2
    uint32_t b_ok = 0x80000000U;
    int64_t c = 5l;                            // EXPECT 7.3
    int64_t c_ok = 5L;
    char *s = "text";                          // EXPECT 7.4
    const char *s_ok = "text";
    uint32_t d = UINT32_C(5u);                 // EXPECT 7.5
    uint8_t e = UINT8_C(5);                    // EXPECT 7.6
    (void)a; (void)b; (void)b_ok; (void)c; (void)c_ok; (void)s; (void)s_ok; (void)d; (void)e;
}
