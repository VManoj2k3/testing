/* Chapter 23: generic selections (C11). */
#include <stdint.h>

void ch23(int32_t x)
{
    int32_t a = _Generic(x, int32_t: 1, default: 0);   // EXPECT 23.1
    int32_t b = _Generic(x++, int32_t: 1, default: 0); // EXPECT 23.2
    int32_t c = _Generic(x, default: 0);               // EXPECT 23.3
    int32_t d = _Generic(x, const int32_t: 1, default: 0); // EXPECT 23.4
    int32_t *p = &x;
    int32_t e = _Generic(p, void *: 1, default: 0);    // EXPECT 23.5
    int32_t f = _Generic('a', char: 1, default: 0);    // EXPECT 23.6
#define TWICE(v) _Generic((v), int32_t: (v) + (v), default: 0)
    int32_t g = TWICE(x);                              // EXPECT 23.7
    int32_t h = _Generic(x, int32_t: 1, default: 0, int16_t: 2); // EXPECT 23.8
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h;
}
