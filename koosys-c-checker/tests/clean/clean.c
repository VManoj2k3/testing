/* A small, intentionally MISRA-compliant module: findings here are false alarms. */
#include "clean.h"

uint32_t g_clean_counter = 0U;

int32_t clean_sum(const int32_t *p_items, uint32_t count)
{
    int32_t l_total = 0;
    uint32_t l_i;
    for (l_i = 0U; l_i < count; l_i++)
    {
        l_total += p_items[l_i];
    }
    g_clean_counter++;
    return l_total;
}

bool clean_find(const clean_item_t *p_items, uint32_t count, uint8_t id, int32_t *p_value)
{
    bool l_found = false;
    uint32_t l_i;
    for (l_i = 0U; (l_i < count) && (!l_found); l_i++)
    {
        if (p_items[l_i].id == id)
        {
            *p_value = p_items[l_i].value;
            l_found = true;
        }
    }
    return l_found;
}

int32_t clean_classify(int32_t level)
{
    int32_t l_result;
    switch (level)
    {
        case 0:
            l_result = 10;
            break;
        case 1:
            l_result = CLEAN_MAX(level, 20);
            break;
        default:
            l_result = -1;
            break;
    }
    if (CLEAN_IS_INT(level))
    {
        l_result += 1;
    }
    else
    {
        l_result -= 1;
    }
    return l_result;
}
