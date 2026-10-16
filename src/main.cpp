/*
 *
 *    Copyright (c) 2020 Project CHIP Authors
 *    Copyright (c) 2019 Google LLC.
 *    All rights reserved.
 *
 *    Licensed under the Apache License, Version 2.0 (the "License");
 *    you may not use this file except in compliance with the License.
 *    You may obtain a copy of the License at
 *
 *        http://www.apache.org/licenses/LICENSE-2.0
 *
 *    Unless required by applicable law or agreed to in writing, software
 *    distributed under the License is distributed on an "AS IS" BASIS,
 *    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *    See the License for the specific language governing permissions and
 *    limitations under the License.
 */

#include "sl_component_catalog.h"
// Use sl_system for projects upgraded to 2025.6, identified by the presence of SL_CATALOG_CUSTOM_MAIN_PRESENT
#if defined(SL_CATALOG_CUSTOM_MAIN_PRESENT)
#include "sl_system_init.h"
#else
#include "sl_main_init.h"
#endif
#include <MatterConfig.h>
#include "em_cmu.h"
#include "em_gpio.h"
#include "sl_sleeptimer.h"
#include "sl_udelay.h"
#include <lib/support/logging/CHIPLogging.h>
#include <platform/silabs/tracing/SilabsTracingMacros.h>

#ifndef MAILBOX_RADIO_GATED_SWITCH
#define MAILBOX_RADIO_GATED_SWITCH 1
#endif
#if MAILBOX_RADIO_GATED_SWITCH
#include "em_core.h"
#include "em_prs.h"
#endif

using TimeTraceOperation = chip::Tracing::Silabs::TimeTraceOperation;

namespace {
void InitRadioSwitch()
{
    GPIO_PinModeSet(gpioPortB, 4, gpioModePushPull, 0); // onboard antenna
    GPIO_PinModeSet(gpioPortB, 5, gpioModePushPull, 1); // FM8625H supply
#if MAILBOX_RADIO_GATED_SWITCH
    // Use hardware radio activity for both Thread and BLE.
    // MCU sleep callbacks do not describe every autonomous radio operation.
    // RAC_ACTIVE is broader than PAEN/LNAEN, but its lead time still needs
    // board validation against the FM8625H's maximum 10 us supply startup.
    CMU_ClockEnable(cmuClock_PRS, true);
    CORE_DECLARE_IRQ_STATE;
    CORE_ENTER_CRITICAL();
    const int channel = PRS_GetFreeChannel(prsTypeAsync);
    // Only asynchronous channels 0..5 can drive port B on the MG24. Existing
    // SDK reservations are already visible here; never overwrite a channel.
    if (channel >= 0 && channel <= 5)
    {
        PRS_ConnectSignal(static_cast<unsigned>(channel), prsTypeAsync, prsSignalRACL_ACTIVE);
        PRS_PinOutput(static_cast<unsigned>(channel), prsTypeAsync, gpioPortB, 5);
    }
    CORE_EXIT_CRITICAL();
    if (channel < 0 || channel > 5)
    {
        ChipLogError(AppServer, "No antenna-switch PRS channel; keeping RF switch powered");
        return;
    }
    ChipLogProgress(AppServer, "Radio-gated antenna switch: PRS channel %d", channel);
#endif
}

#if !MAILBOX_CONSOLE_KEEP_AWAKE
constexpr uint32_t kDebugRecoveryMs = 5000;
sl_sleeptimer_timer_handle_t sDebugRecoveryTimer{};

void ReleaseDebugPins(sl_sleeptimer_timer_handle_t *, void *)
{
    // PA2/SWDIO and PA1/SWCLK connect to the USB-only SAMD11. Ordinary
    // GPIO mode does not remove the debug function's reset-default pulls.
    // Reset restores SWD; leave a recovery window of at least three seconds
    // as required by the MG24 reference manual, section 24.3.9.3.
    GPIO_PinModeSet(gpioPortA, 2, gpioModeDisabled, 0);
    GPIO_PinModeSet(gpioPortA, 1, gpioModeDisabled, 0);
    GPIO_DbgSWDIOEnable(false);
    GPIO_DbgSWDClkEnable(false);
}
#endif

void SleepUnusedFlash()
{
    // Onboard Puya P25Q32SH: /CS=PA6, SCLK=PA0, SI=PB0, SO=PB1.
    // The application uses internal flash. Send the non-writing 0xB9 command
    // in SPI mode 0 to avoid the external device's standby current.
    constexpr uint8_t command = 0xb9;
    GPIO_PinModeSet(gpioPortA, 6, gpioModePushPull, 1);
    GPIO_PinModeSet(gpioPortA, 0, gpioModePushPull, 0);
    GPIO_PinModeSet(gpioPortB, 0, gpioModePushPull, 0);
    GPIO_PinModeSet(gpioPortB, 1, gpioModeDisabled, 0);
    sl_udelay_wait(150); // Flash power-on tVSL minimum; /CS stays high.
    GPIO_PinOutClear(gpioPortA, 6);
    for (uint8_t mask = 0x80; mask != 0; mask >>= 1)
    {
        if (command & mask)
            GPIO_PinOutSet(gpioPortB, 0);
        else
            GPIO_PinOutClear(gpioPortB, 0);
        sl_udelay_wait(1);
        GPIO_PinOutSet(gpioPortA, 0);
        sl_udelay_wait(1);
        GPIO_PinOutClear(gpioPortA, 0);
    }
    GPIO_PinOutSet(gpioPortA, 6);
    GPIO_PinOutClear(gpioPortB, 0);
    sl_udelay_wait(10); // tDP maximum is 3 us.
}
} // namespace

// This is a User definable function in sl_main context, called by sl_main_init before the kernel is started
void app_init_early(void)
{
    SILABS_TRACE_BEGIN(chip::Tracing::Silabs::TimeTraceOperation::kBootup);
    SILABS_TRACE_BEGIN(chip::Tracing::Silabs::TimeTraceOperation::kSilabsInit);
}

// This is a User definable function, in sl_main context, called by start_task_handler once the silabs platform is fully
// initialized.
void app_init(void)
{
    SILABS_TRACE_END(chip::Tracing::Silabs::TimeTraceOperation::kSilabsInit);
    SILABS_TRACE_BEGIN(chip::Tracing::Silabs::TimeTraceOperation::kMatterInit);
    // XIAO RF switch and unused Sense peripherals, before either radio starts.
    CMU_ClockEnable(cmuClock_GPIO, true);
    InitRadioSwitch();
    GPIO_PinModeSet(gpioPortD, 5, gpioModePushPull, 0); // onboard IMU off
    GPIO_PinModeSet(gpioPortC, 8, gpioModePushPull, 0); // microphone off
    SleepUnusedFlash();
    GPIO_PinModeSet(gpioPortD, 3, gpioModePushPull, 0); // battery divider off
#if !MAILBOX_CONSOLE_KEEP_AWAKE
    // These pins connect directly to the USB-powered SAMD11. Do not drive
    // its unpowered inputs from the battery rail in the normal build.
    GPIO_PinModeSet(gpioPortA, 8, gpioModeDisabled, 0);
    GPIO_PinModeSet(gpioPortA, 9, gpioModeDisabled, 0);
    GPIO_PinModeSet(gpioPortA, 7, gpioModePushPull, 1); // active-low LED off
    const sl_status_t status = sl_sleeptimer_start_timer_ms(
        &sDebugRecoveryTimer, kDebugRecoveryMs, ReleaseDebugPins, nullptr, 0,
        SL_SLEEPTIMER_NO_HIGH_PRECISION_HF_CLOCKS_REQUIRED_FLAG);
    if (status == SL_STATUS_OK)
    {
        ChipLogProgress(AppServer, "SWD pin release scheduled after %u ms", static_cast<unsigned>(kDebugRecoveryMs));
    }
    else
    {
        ChipLogError(AppServer, "SWD recovery timer failed: 0x%lx; debug pins remain enabled", static_cast<unsigned long>(status));
    }
#endif
    // Initialize the matter application. For example, create periodic timer(s) or
    // task(s).
    SilabsMatterConfig::AppInit();
}

#if defined(SL_CATALOG_CUSTOM_MAIN_PRESENT)
int main(void)
{
    app_init_early();
    sl_system_init();
    app_init();
}
#endif
