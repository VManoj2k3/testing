/* Chapters 1-4: standard C, unused code, comments, character sets. */
#include <stdint.h>

typedef int32_t unused_type_t;                 // EXPECT 2.3
struct unused_tag { int32_t a; };              // EXPECT 2.4
#define UNUSED_MACRO 1                         // EXPECT 2.5
static int32_t unused_object;                  // EXPECT 2.8

int32_t ch02_unreachable(int32_t x)
{
    int32_t r = x;
    return r;
    r = 2;                                     // EXPECT 2.1
}

void ch02_dead(void)
{
    int32_t y = 0;
    y = 3;                                     // EXPECT 2.2
}

void ch02_label(void)
{
unused_label:                                  // EXPECT 2.6
    ;
}

static int32_t ch02_param(int32_t used, int32_t unused) // EXPECT 2.7
{
    return used;
}

/* a nested /* comment start */                // EXPECT 3.1
// line splice in comment \
   continues here                              // EXPECT 3.2

const char ch04_esc[] = "\x41g";               // EXPECT 4.1
const char ch04_ok[] = "\x41" "g";
const char ch04_tri[] = "what??!";             // EXPECT 4.2

int32_t ch01_ext(void)
{
    int32_t v = ({ 1; });                      // EXPECT 1.2
    return v + ch02_param(1, 2);
}

int32_t ch01_ub(int32_t a)
{
    int32_t z = 0;
    return a / z;                              // EXPECT 1.3
}

_Noreturn void ch01_obsolete_style();          // EXPECT 1.5
