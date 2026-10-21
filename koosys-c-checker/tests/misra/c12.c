/* Chapter 12: expressions. */
#include <stdint.h>
#include <stdatomic.h>

struct s12 { int32_t m; };

int32_t ch12(int32_t a, int32_t b, uint8_t u, int32_t arr[10])
{
    int32_t r1 = a + b * a - b;                // EXPECT 12.1
    uint8_t r2 = u << 9;                       // EXPECT 12.2
    int32_t r3 = (a++, b);                     // EXPECT 12.3
    uint32_t r4 = 0U - 1U;                     // EXPECT 12.4
    uint32_t r5 = sizeof(arr);                 // EXPECT 12.5
    _Atomic struct s12 as;
    int32_t r6 = as.m;                         // EXPECT 12.6
    return r1 + r2 + r3 + (int32_t)r4 + (int32_t)r5 + r6;
}
