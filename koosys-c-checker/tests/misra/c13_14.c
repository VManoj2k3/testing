/* Chapters 13-14: side effects, control statement expressions. */
#include <stdint.h>
#include <stdbool.h>

extern int32_t f13(void);
extern volatile int32_t v13;

void ch13(int32_t a, int32_t b, int32_t arr[4])
{
    int32_t init[2] = { a++, b };              // EXPECT 13.1
    int32_t r2 = arr[a] + a++;                 // EXPECT 13.2
    int32_t r3 = a++ + f13();                  // EXPECT 13.3
    int32_t r4;
    int32_t r5 = (r4 = b);                     // EXPECT 13.4
    if ((a > 0) && (b++ > 0)) { }              // EXPECT 13.5
    uint32_t r6 = sizeof(a++);                 // EXPECT 13.6
    (void)init; (void)r2; (void)r3; (void)r5; (void)r6;
}

void ch14(int32_t n)
{
    float fl;
    for (fl = 0.0f; fl < 1.0f; fl += 0.1f) { } // EXPECT 14.1
    for (int32_t i = 0; i < n; i++) { i = n; } // EXPECT 14.2
    uint32_t u = 1U;
    if (u >= 0U) { }                           // EXPECT 14.3
    if (n) { }                                 // EXPECT 14.4
    if (n != 0) { }
}
