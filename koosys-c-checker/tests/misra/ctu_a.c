/* Cross-file rules, part A (pair with ctu_b.c). */
#include <stdint.h>
int32_t ctu_shared_name;
static int32_t ctu_static_clash(void) { return 0; }
int32_t ctu_twice_defined = 1;
int32_t ctu_only_here(void) { return ctu_static_clash(); } // EXPECT 8.7
int32_t ctu_use(void) { return ctu_only_here(); }
