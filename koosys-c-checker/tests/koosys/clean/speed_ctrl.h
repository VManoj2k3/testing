// File: speed_ctrl.h
// Purpose: Speed controller interface (KooSys-compliant fixture)
// Author: KooSys test
// Date: 2026-10-21
#ifndef SPEED_CTRL_H
#define SPEED_CTRL_H

#include <stdint.h>
#include "Std_Types.h"

#define SPEED_CTRL_MAX_RPM 6000U

typedef uint16_t speed_rpm_t;

typedef struct
{
    speed_rpm_t target;
    speed_rpm_t actual;
} speed_state_t;

extern uint32_t speed_ctrl_cycles;

/**
 * @brief Speed_Ctrl_Update: apply one control step.
 * @param p_state controller state (not NULL)
 * @return E_OK on success, E_NOT_OK if the target is out of range
 * @req SWRS-SPD-012
 */
extern Std_ReturnType Speed_Ctrl_Update(speed_state_t *p_state);

#endif
