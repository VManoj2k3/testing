/* Chapter 8: declarations and definitions. */
#include <stdint.h>
#include "c08.h"

static n;                                      // EXPECT 8.1
int32_t ch08_noproto();                        // EXPECT 8.2
int32_t ch08_unnamed(int32_t);                 // EXPECT 8.2
int32_t ch08_names(int32_t b) { return b; }    // EXPECT 8.3
int32_t ch08_novisible(void) { return 0; }     // EXPECT 8.4
int32_t ch08_twice;                            // EXPECT 8.5
static int32_t ch08_internal(void);
int32_t ch08_internal(void) { return 1; }      // EXPECT 8.8
static int32_t ch08_blockscope;                // EXPECT 8.9
int32_t ch08_use_block(void) { return ch08_blockscope + ch08_internal(); }
inline int32_t ch08_inline(void) { return 2; } // EXPECT 8.10
extern int32_t ch08_arr[];                     // EXPECT 8.11
enum ch08_e { E_A = 1, E_B, E_C = 2 };         // EXPECT 8.12
int32_t ch08_constptr(int32_t *p) { return *p; } // EXPECT 8.13
void ch08_restrict(int32_t * restrict p);      // EXPECT 8.14
_Alignas(8) int32_t ch08_al;
extern _Alignas(16) int32_t ch08_al;           // EXPECT 8.15
_Alignas(0) int32_t ch08_al0;                  // EXPECT 8.16
_Alignas(8) _Alignas(16) int32_t ch08_al2;     // EXPECT 8.17
