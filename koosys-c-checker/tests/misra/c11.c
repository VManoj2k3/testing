/* Chapter 11: pointer type conversions. */
#include <stdint.h>
#include <stddef.h>

struct incomplete;
typedef void (*fp_t)(void);

void ch11(fp_t fp, struct incomplete *inc, int32_t *pi, void *pv, const int32_t *pc)
{
    uintptr_t a = (uintptr_t)fp;               // EXPECT 11.1
    int32_t *b = (int32_t *)inc;               // EXPECT 11.2
    int16_t *c = (int16_t *)pi;                // EXPECT 11.3
    uintptr_t d = (uintptr_t)pi;               // EXPECT 11.4
    int32_t *e = (int32_t *)pv;                // EXPECT 11.5
    uint32_t f = (uint32_t)pv;                 // EXPECT 11.6
    float g = (float)(uintptr_t)pi;            // EXPECT 11.7
    int32_t *h = (int32_t *)pc;                // EXPECT 11.8
    int32_t *i = 0;                            // EXPECT 11.9
    int32_t *i_ok = NULL;
    (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h; (void)i; (void)i_ok;
}

_Atomic void *ch11_atomic_void;                // EXPECT 11.10
