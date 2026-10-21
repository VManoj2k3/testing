#ifndef CLEAN_H
#define CLEAN_H
#include <stdint.h>
#include <stdbool.h>

#define CLEAN_MAX(a, b) (((a) > (b)) ? (a) : (b))
#define CLEAN_IS_INT(x) _Generic((x), int32_t: true, default: false)

typedef struct
{
    uint8_t id;
    int32_t value;
} clean_item_t;

extern uint32_t g_clean_counter;
extern int32_t clean_sum(const int32_t *p_items, uint32_t count);
extern bool clean_find(const clean_item_t *p_items, uint32_t count, uint8_t id, int32_t *p_value);
extern int32_t clean_classify(int32_t level);
#endif
