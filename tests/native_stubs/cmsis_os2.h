// Host test stand-in for the CMSIS-RTOS2 declarations used by Bma400Motion.
#pragma once

#include <stdint.h>

typedef enum
{
    osKernelInactive = 0,
    osKernelReady = 1,
    osKernelRunning = 2,
    osKernelLocked = 3,
} osKernelState_t;

typedef enum
{
    osOK = 0,
    osErrorResource = -3,
} osStatus_t;

osKernelState_t osKernelGetState(void);
uint32_t osKernelGetTickFreq(void);
osStatus_t osDelay(uint32_t ticks);
