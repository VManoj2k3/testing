/* Chapters 5-6: identifiers, bit-fields. */
#include <stdint.h>

int32_t engine_speed_value_in_rpm_sensor_a;
int32_t engine_speed_value_in_rpm_sensor_b;    // EXPECT 5.1

static int32_t g_shadow;
void ch05_shadow(void)
{
    int32_t g_shadow = 1;                      // EXPECT 5.3
    (void)g_shadow;
}

#define mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm_1 1
#define mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm_2 2 // EXPECT 5.4

#define speed 3
int32_t ch05_macro_clash(void) { int32_t speed_local = speed; return speed_local; }
static int32_t speed_var;
#undef speed
static int32_t speed;                          // EXPECT 5.5

typedef int32_t my_type_t;
void ch05_typedef(void) { int32_t my_type_t = 0; (void)my_type_t; } // EXPECT 5.6

struct tag_a { int32_t x; };
void ch05_tag(void) { int32_t tag_a = 0; (void)tag_a; } // EXPECT 5.7

struct bits {
    int plain : 2;                             // EXPECT 6.1
    signed int one : 1;                        // EXPECT 6.2
    unsigned int ok : 3;
};

union u_bits {
    unsigned int bf : 3;                       // EXPECT 6.3
    uint32_t w;
};

void ch05_scope(void)
{
    int32_t vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv_1 = 0;
    int32_t vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv_2 = 0;                        // EXPECT 5.2
    (void)vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv_1; (void)vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv_2;
}
