/* Cross-file rules, part B (pair with ctu_a.c). */
#include <stdint.h>
static int32_t ctu_shared_name;                // EXPECT 5.8
static int32_t ctu_static_clash(void) { return 1; } // EXPECT 5.9
int32_t ctu_twice_defined = 2;                 // EXPECT 8.6
