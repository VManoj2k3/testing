/* Chapters 18-19: pointers and arrays, overlapping storage. */
#include <stdint.h>
#include <string.h>

struct flex { int32_t n; int32_t data[]; };    // EXPECT 18.7

int32_t *ch18_dangling(void)
{
    int32_t local = 1;
    return &local;                             // EXPECT 18.6
}

struct big { int32_t a[4]; };
extern struct big make_big(void);

void ch18(int32_t n)
{
    int32_t a[4] = { 0, 0, 0, 0 };
    int32_t b[4] = { 0, 0, 0, 0 };
    int32_t *p = a;
    int32_t *q = &a[6];                        // EXPECT 18.1
    int32_t diff = (int32_t)(&b[1] - &a[0]);   // EXPECT 18.2
    if (p < b) { }                             // EXPECT 18.3
    p = p + 1;                                 // EXPECT 18.4
    int32_t ***ppp = NULL;                     // EXPECT 18.5
    int32_t vla[n];                            // EXPECT 18.8
    int32_t *tmp = make_big().a;               // EXPECT 18.9
    int32_t (*pv)[n];                          // EXPECT 18.10
    (void)q; (void)diff; (void)ppp; (void)vla; (void)tmp; (void)pv;
}

union u19 { int32_t i; float f; };             // EXPECT 19.2

void ch19(void)
{
    char buf[8] = "abcdefg";
    memcpy(&buf[1], &buf[0], 4U);              // EXPECT 19.1
}
