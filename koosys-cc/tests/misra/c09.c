/* Chapter 9: initialization. */
#include <stdint.h>
#include <stdatomic.h>

struct pt { int32_t x; int32_t y; };

int32_t ch09(void)
{
    int32_t u;
    int32_t r = u;                             // EXPECT 9.1
    int32_t arr2[2][2] = { 1, 2, 3, 4 };       // EXPECT 9.2
    int32_t part[3] = { 1, 2 };                // EXPECT 9.3
    int32_t twice[3] = { [0] = 1, [0] = 2, [1] = 0, [2] = 0 }; // EXPECT 9.4
    int32_t nosize[] = { [0] = 1 };            // EXPECT 9.5
    struct pt chain[1] = { [0].x = 1, 2 };     // EXPECT 9.6
    atomic_int at;
    int32_t v = atomic_load(&at);              // EXPECT 9.7
    return r + arr2[0][0] + part[0] + twice[0] + nosize[0] + chain[0].x + v;
}
