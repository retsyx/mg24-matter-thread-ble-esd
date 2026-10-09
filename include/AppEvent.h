// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "BaseAppEvent.h"

struct AppEvent : public BaseAppEvent
{
    enum AppEventTypes
    {
        kEventType_Motion = BaseAppEvent::kEventType_Max + 1,
        kEventType_MotionExpired,
        kEventType_SensorRetry,
        kEventType_BatterySample,
        kEventType_Status,
        kEventType_Commission,
    };

    bool Simulated = false;
};
