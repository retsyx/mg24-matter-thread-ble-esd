// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "silabs_utils.h"

#define APP_TASK_NAME "Mailbox"
#define BLE_DEV_NAME "MG24-Mailbox"
#define APP_TASK_STACK_SIZE 4096
#define APP_EVENT_QUEUE_SIZE 16

#define MAILBOX_MOTION_HOLD_MS 5000u
#define MAILBOX_SENSOR_RETRY_MS 60000u
#define MAILBOX_BATTERY_INTERVAL_MS (24u * 60u * 60u * 1000u)
#define MAILBOX_BMA400_ADDRESS 0x14u

// USB can put voltage on the charger output even when no battery is fitted.
// Enable this explicitly when a rechargeable battery has been connected.
#ifndef MAILBOX_BATTERY_INSTALLED
#define MAILBOX_BATTERY_INSTALLED 0
#endif
