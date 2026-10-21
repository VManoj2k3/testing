/* Chapter 17: functions. */
#include <stdint.h>
#include <stdarg.h>                            // EXPECT 17.1

extern int32_t f17(void);

int32_t ch17_rec(int32_t n)
{
    if (n <= 0) { n = 0; } else { n = ch17_rec(n - 1); } // EXPECT 17.2
    return n;
}

static int32_t ch17_ind_b(int32_t n);
static int32_t ch17_ind_a(int32_t n) { return (n > 0) ? ch17_ind_b(n - 1) : 0; }
static int32_t ch17_ind_b(int32_t n) { return ch17_ind_a(n); } // EXPECT 17.2

int32_t ch17_implicit(void) { return undeclared_fn(); } // EXPECT 17.3

int32_t ch17_noreturn_val(int32_t a)
{
    if (a > 0) { return 1; }
}                                              // EXPECT 17.4

void take5(int32_t arr[5]);
void ch17_args(void)
{
    int32_t three[3] = { 0, 0, 0 };
    take5(three);                              // EXPECT 17.5
}

void ch17_static_param(int32_t arr[static 4]); // EXPECT 17.6

void ch17_unused_ret(void)
{
    f17();                                     // EXPECT 17.7
    (void)f17();
}

void ch17_modparam(int32_t p)
{
    p = 3;                                     // EXPECT 17.8
}

_Noreturn void ch17_nr(int32_t a) { if (a) { } } // EXPECT 17.9
_Noreturn int32_t ch17_nr_int(void);           // EXPECT 17.10
void ch17_forever(void) { for (;;) { } }       // EXPECT 17.11

void ch17_fnid(void)
{
    void (*p)(void) = ch17_forever;            // EXPECT 17.12
    (void)p;
}

typedef int32_t fn_t(void);
const fn_t ch17_qualified;                     // EXPECT 17.13
