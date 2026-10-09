// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "AppEvent.h"
#include "BaseApplication.h"
#include "Bma400Motion.h"

#include <app/clusters/occupancy-sensor-server/occupancy-sensor-server.h>
#include <cmsis_os2.h>

class AppTask : public BaseApplication
{
public:
    static AppTask & GetAppTask() { return sAppTask; }
    CHIP_ERROR StartAppTask();
    static void AppTaskMain(void * argument);
    static void ButtonEventHandler(uint8_t button, uint8_t action);

    // Diagnostic requests follow the same task/timer path as the real sensor.
    static bool QueueMotion();
    static bool QueueStatus();
    static bool QueueBatterySample();
    static bool QueueCommission();

private:
    CHIP_ERROR AppInit() override;
    static void MotionInterrupt(uint8_t interruptNumber);
    static void MotionTimerExpired(void * argument);
    static void SensorRetryTimerExpired(void * argument);
    static void BatteryTimerExpired(void * argument);
    static void HandleMailboxEvent(AppEvent * event);
    static bool QueueMailboxEvent(uint16_t type, bool simulated = false);

    void RearmSensor();
    void MotionDetected(bool simulated);
    void MotionExpired();
    void SetOccupancy(bool occupied);
    void SampleBattery();
    void PrintStatus();
    void OpenCommissioningWindow();

    static AppTask sAppTask;
    Bma400Motion mSensor;
    chip::app::Clusters::OccupancySensing::Instance mOccupancy{
        chip::BitMask<chip::app::Clusters::OccupancySensing::Feature>(
            chip::app::Clusters::OccupancySensing::Feature::kPassiveInfrared)
    };
    osTimerId_t mMotionTimer = nullptr;
    osTimerId_t mSensorRetryTimer = nullptr;
    osTimerId_t mBatteryTimer = nullptr;
    bool mSensorReady = false;
    bool mOccupied = false;
    uint32_t mMotionCount = 0;
};
