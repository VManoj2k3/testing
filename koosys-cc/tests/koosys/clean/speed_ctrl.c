// File: speed_ctrl.c
// Purpose: Speed controller (KooSys-compliant fixture)
// Author: KooSys test
// Date: 2026-10-21
#include <assert.h>
#include "speed_ctrl.h"

uint32_t speed_ctrl_cycles = 0U;
static uint16_t l_step = 10U;

/**
 * @brief Speed_Ctrl_Update: apply one control step.
 * @param p_state controller state (not NULL)
 * @return E_OK on success, E_NOT_OK if the target is out of range
 * @req SWRS-SPD-012
 */
Std_ReturnType Speed_Ctrl_Update(speed_state_t *p_state)
{
    Std_ReturnType ret = E_NOT_OK;
    speed_rpm_t *p_actual = NULL;
    uint8_t i;

    assert(p_state != NULL);
    assert(l_step > 0U);
    if (p_state->target <= SPEED_CTRL_MAX_RPM) {
        p_actual = &p_state->actual;
        for (i = 0U; i < 4U; i++) {
            if (*p_actual < p_state->target) {
                *p_actual = (speed_rpm_t)(*p_actual + l_step);
            }
        }
        speed_ctrl_cycles++;
        ret = E_OK;
    }
    return ret;
}
