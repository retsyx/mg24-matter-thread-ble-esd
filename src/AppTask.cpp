// SPDX-License-Identifier: GPL-3.0-or-later
// Native Silicon Labs Matter application for the XIAO MG24 mailbox sensor.

#include "AppTask.h"
#include "AppConfig.h"
#include "BatteryMonitor.h"

#include "em_cmu.h"
#include "em_gpio.h"
#include "gpiointerrupt.h"
#include "sl_gpio.h"
#include "sl_i2cspm.h"

#include <app-common/zap-generated/attributes/Accessors.h>
#include <app/server/Server.h>
#include <app/clusters/power-source-server/power-source-server.h>
#include <headers/ProvisionManager.h>
#include <setup_payload/ManualSetupPayloadGenerator.h>
#include <setup_payload/QRCodeSetupPayloadGenerator.h>
#include <setup_payload/QRCodeSetupPayloadParser.h>
#include <lib/support/CodeUtils.h>
#include <platform/CHIPDeviceLayer.h>
#include <platform/silabs/platformAbstraction/SilabsPlatform.h>

#if CHIP_CONFIG_ENABLE_ICD_SERVER
#include <app/icd/server/ICDNotifier.h>
#endif

#ifdef ENABLE_CHIP_SHELL
#include <lib/shell/Engine.h>
#include <cstring>
#endif

using namespace chip;
using namespace chip::app::Clusters;
using namespace chip::DeviceLayer;

namespace {
constexpr EndpointId kMotionEndpoint = 1;
constexpr EndpointId kBatteryEndpoint = 2;
constexpr unsigned kMotionInterruptNumber = 2; // XIAO D2 = PC2, BMA400 INT1.
constexpr uint32_t kMotionInterruptMask = 1u << kMotionInterruptNumber;
osMessageQueueId_t sMailboxQueue = nullptr;
volatile uint32_t sDroppedInterrupts = 0;

void PrintPairingCode()
{
    char qr[chip::QRCodeBasicSetupPayloadGenerator::kMaxQRCodeBase38RepresentationLength + 1];
    chip::MutableCharSpan qrSpan(qr);
    auto error = chip::DeviceLayer::Silabs::Provision::Manager::GetInstance().GetStorage().GetSetupPayload(qrSpan);
    if (error != CHIP_NO_ERROR)
        return;
    chip::SetupPayload payload;
    chip::QRCodeSetupPayloadParser parser(std::string(qrSpan.data(), qrSpan.size()));
    if (parser.populatePayload(payload) != CHIP_NO_ERROR)
        return;
    char manual[32];
    chip::MutableCharSpan manualSpan(manual);
    if (chip::ManualSetupPayloadGenerator(payload).payloadDecimalStringRepresentation(manualSpan) == CHIP_NO_ERROR)
        ChipLogProgress(AppServer, "Manual pairing code: %.*s", static_cast<int>(manualSpan.size()), manualSpan.data());
}


uint32_t MillisecondsToTicks(uint32_t milliseconds)
{
    const uint64_t ticks = (static_cast<uint64_t>(milliseconds) * osKernelGetTickFreq() + 999u) / 1000u;
    return static_cast<uint32_t>(ticks == 0 ? 1 : ticks);
}

#ifdef ENABLE_CHIP_SHELL
CHIP_ERROR MailboxCommand(int argc, char ** argv)
{
    if (argc != 1)
    {
        Shell::streamer_printf(Shell::streamer_get(), "Usage: mailbox motion|status|battery|commission\r\n");
        return CHIP_ERROR_INVALID_ARGUMENT;
    }
    bool queued = false;
    if (strcmp(argv[0], "motion") == 0)
        queued = AppTask::QueueMotion();
    else if (strcmp(argv[0], "status") == 0)
        queued = AppTask::QueueStatus();
    else if (strcmp(argv[0], "battery") == 0)
        queued = AppTask::QueueBatterySample();
    else if (strcmp(argv[0], "commission") == 0)
        queued = AppTask::QueueCommission();
    else
        return CHIP_ERROR_INVALID_ARGUMENT;

    return queued ? CHIP_NO_ERROR : CHIP_ERROR_NO_MEMORY;
}

const Shell::shell_command_t kMailboxCommands[] = {
    { MailboxCommand, "mailbox", "Mailbox diagnostics: motion, status, battery, commission" },
};
#endif
} // namespace

AppTask AppTask::sAppTask;

CHIP_ERROR AppTask::StartAppTask()
{
    return BaseApplication::StartAppTask(AppTaskMain);
}

void AppTask::AppTaskMain(void * argument)
{
    sMailboxQueue = *static_cast<osMessageQueueId_t *>(argument);
    CHIP_ERROR error = sAppTask.Init();
    if (error != CHIP_NO_ERROR)
        appError(error);

    ChipLogProgress(AppServer, "Mailbox AppTask started; motion endpoint=1 battery endpoint=2");
    AppEvent event{};
    while (true)
    {
        if (osMessageQueueGet(sMailboxQueue, &event, nullptr, osWaitForever) == osOK)
            sAppTask.DispatchEvent(&event);
    }
}

CHIP_ERROR AppTask::AppInit()
{
    DeviceLayer::Silabs::GetPlatform().SetButtonsCb(ButtonEventHandler);

    PlatformMgr().LockChipStack();
    CHIP_ERROR error = mOccupancy.Init();
    if (error == CHIP_NO_ERROR)
    {
        const OccupancySensing::Structs::HoldTimeLimitsStruct::Type limits{
            5, 5, 5
        };
        error = OccupancySensing::SetHoldTimeLimits(kMotionEndpoint, limits);
        if (error == CHIP_NO_ERROR)
            error = OccupancySensing::SetHoldTime(kMotionEndpoint, 5);
    }
    if (error == CHIP_NO_ERROR)
    {
        EndpointId poweredEndpoints[] = { kMotionEndpoint };
        error = PowerSourceServer::Instance().SetEndpointList(kBatteryEndpoint, Span<EndpointId>(poweredEndpoints));
    }
    if (Server::GetInstance().GetFabricTable().FabricCount() == 0)
        PrintPairingCode();
    PlatformMgr().UnlockChipStack();
    ReturnErrorOnFailure(error);

    mMotionTimer = osTimerNew(MotionTimerExpired, osTimerOnce, this, nullptr);
    mSensorRetryTimer = osTimerNew(SensorRetryTimerExpired, osTimerOnce, this, nullptr);
    mBatteryTimer = osTimerNew(BatteryTimerExpired, osTimerOnce, this, nullptr);
    VerifyOrReturnError(mMotionTimer && mSensorRetryTimer && mBatteryTimer, CHIP_ERROR_NO_MEMORY);

    CMU_ClockEnable(cmuClock_GPIO, true);
    GPIO_PinModeSet(gpioPortC, 2, gpioModeInputPull, 0);
    GPIOINT_Init();
    // CMSIS queue calls from the GPIO ISR require a FreeRTOS-safe priority.
    NVIC_SetPriority(GPIO_EVEN_IRQn, 0xff);
    GPIOINT_CallbackRegister(kMotionInterruptNumber, MotionInterrupt);
    GPIO_ExtIntConfig(gpioPortC, 2, kMotionInterruptNumber, true, false, false);

#ifdef ENABLE_CHIP_SHELL
    Shell::Engine::Root().RegisterCommands(kMailboxCommands, 1);
#endif

    SetOccupancy(false);
    RearmSensor();
    SampleBattery();
    return CHIP_NO_ERROR;
}

bool AppTask::QueueMailboxEvent(uint16_t type, bool simulated)
{
    if (sMailboxQueue == nullptr)
        return false;
    AppEvent event{};
    event.Type = type;
    event.Handler = HandleMailboxEvent;
    event.Simulated = simulated;
    // timeout=0 permits this exact call from the GPIO ISR as well as tasks.
    return osMessageQueuePut(sMailboxQueue, &event, 0, 0) == osOK;
}

bool AppTask::QueueMotion() { return QueueMailboxEvent(AppEvent::kEventType_Motion, true); }
bool AppTask::QueueStatus() { return QueueMailboxEvent(AppEvent::kEventType_Status); }
bool AppTask::QueueBatterySample() { return QueueMailboxEvent(AppEvent::kEventType_BatterySample); }
bool AppTask::QueueCommission() { return QueueMailboxEvent(AppEvent::kEventType_Commission); }

void AppTask::MotionInterrupt(uint8_t interruptNumber)
{
    if (interruptNumber != kMotionInterruptNumber)
        return;
    GPIO_IntDisable(kMotionInterruptMask);
    if (!QueueMailboxEvent(AppEvent::kEventType_Motion))
    {
        ++sDroppedInterrupts;
        GPIO_IntEnable(kMotionInterruptMask);
    }
}

void AppTask::MotionTimerExpired(void *)
{
    if (!QueueMailboxEvent(AppEvent::kEventType_MotionExpired))
        osTimerStart(sAppTask.mMotionTimer, MillisecondsToTicks(100));
}

void AppTask::SensorRetryTimerExpired(void *)
{
    if (!QueueMailboxEvent(AppEvent::kEventType_SensorRetry))
        osTimerStart(sAppTask.mSensorRetryTimer, MillisecondsToTicks(MAILBOX_SENSOR_RETRY_MS));
}

void AppTask::BatteryTimerExpired(void *)
{
    if (!QueueMailboxEvent(AppEvent::kEventType_BatterySample))
        osTimerStart(sAppTask.mBatteryTimer, MillisecondsToTicks(1000));
}

void AppTask::HandleMailboxEvent(AppEvent * event)
{
    switch (event->Type)
    {
    case AppEvent::kEventType_Motion:
        sAppTask.MotionDetected(event->Simulated);
        break;
    case AppEvent::kEventType_MotionExpired:
        sAppTask.MotionExpired();
        break;
    case AppEvent::kEventType_SensorRetry:
        if (!sAppTask.mOccupied)
            sAppTask.RearmSensor();
        else
            osTimerStart(sAppTask.mSensorRetryTimer, MillisecondsToTicks(MAILBOX_SENSOR_RETRY_MS));
        break;
    case AppEvent::kEventType_BatterySample:
        sAppTask.SampleBattery();
        break;
    case AppEvent::kEventType_Status:
        sAppTask.PrintStatus();
        break;
    case AppEvent::kEventType_Commission:
        sAppTask.OpenCommissioningWindow();
        break;
    default:
        break;
    }
}

void AppTask::RearmSensor()
{
    GPIO_IntDisable(kMotionInterruptMask);
    I2CSPM_Init_TypeDef config{
        I2C0, SL_GPIO_PORT_C, 5, SL_GPIO_PORT_C, 4,
        0, 100000, i2cClockHLRStandard
    };
    I2CSPM_Init(&config);
    const int8_t result = mSensor.begin(I2C0, MAILBOX_BMA400_ADDRESS);
    mSensorReady = result == BMA400_OK;
    GPIO_IntClear(kMotionInterruptMask);
    if (mSensorReady)
    {
        if (osTimerIsRunning(mSensorRetryTimer))
            osTimerStop(mSensorRetryTimer);
        // The configured BMA400 output drives both levels; no pull current.
        GPIO_PinModeSet(gpioPortC, 2, gpioModeInput, 0);
        GPIO_IntEnable(kMotionInterruptMask);
        ChipLogProgress(AppServer, "BMA400 ready: address=0x%02x chip_id=0x%02x SDA=PC4 SCL=PC5 INT1=PC2",
                        MAILBOX_BMA400_ADDRESS, mSensor.chipId());
    }
    else
    {
        GPIO_PinModeSet(gpioPortC, 2, gpioModeInputPull, 0);
        ChipLogError(AppServer, "BMA400 unavailable (error=%d); retry in 60 s; Matter commissioning remains available", result);
        osTimerStart(mSensorRetryTimer, MillisecondsToTicks(MAILBOX_SENSOR_RETRY_MS));
    }
}

void AppTask::MotionDetected(bool simulated)
{
    if (mOccupied)
        return;
    if (!simulated && !mSensorReady)
        return;

    GPIO_IntDisable(kMotionInterruptMask);
    if (!simulated)
    {
        uint16_t interruptStatus = 0;
        const int8_t result = mSensor.readInterruptStatus(interruptStatus);
        ChipLogProgress(AppServer, "BMA400 motion interrupt status=0x%04x result=%d", interruptStatus, result);
        if (result != BMA400_OK)
        {
            RearmSensor();
            return;
        }
    }
    ++mMotionCount;
    SetOccupancy(true);
    ChipLogProgress(AppServer, "Mailbox motion #%lu (%s), clear after 5000 ms",
                    static_cast<unsigned long>(mMotionCount), simulated ? "shell test" : "BMA400");
    if (osTimerStart(mMotionTimer, MillisecondsToTicks(MAILBOX_MOTION_HOLD_MS)) != osOK)
    {
        ChipLogError(AppServer, "Failed to start motion timer; clearing occupancy");
        MotionExpired();
    }
}

void AppTask::MotionExpired()
{
    SetOccupancy(false);
    // Resetting the sensor captures the lid's new orientation as its baseline.
    RearmSensor();
}

void AppTask::SetOccupancy(bool occupied)
{
    BitMask<OccupancySensing::OccupancyBitmap> state;
    if (occupied)
        state.Set(OccupancySensing::OccupancyBitmap::kOccupied);
    PlatformMgr().LockChipStack();
#if CHIP_CONFIG_ENABLE_ICD_SERVER
    app::ICDNotifier::GetInstance().NotifyNetworkActivityNotification();
#endif
    const auto status = OccupancySensing::Attributes::Occupancy::Set(kMotionEndpoint, state);
    PlatformMgr().UnlockChipStack();
    mOccupied = occupied;
    ChipLogProgress(AppServer, "Mailbox occupancy=%u endpoint=1 update_status=0x%02x", occupied, static_cast<unsigned>(status));
}

void AppTask::SampleBattery()
{
    app::DataModel::Nullable<uint32_t> voltage;
    app::DataModel::Nullable<uint8_t> percentage;
    bool present = false;
    bool low = false;
#if MAILBOX_BATTERY_INSTALLED
    uint32_t millivolts = 0;
    if (ReadBatteryMillivolts(millivolts))
    {
        present = true;
        voltage.SetNonNull(millivolts);
        const uint32_t bounded = millivolts < 3500 ? 3500 : (millivolts > 4200 ? 4200 : millivolts);
        const uint8_t percent = static_cast<uint8_t>((bounded - 3500) * 100 / 700);
        percentage.SetNonNull(static_cast<uint8_t>(percent * 2));
        low = percent < 20;
        ChipLogProgress(AppServer, "Mailbox battery=%lu mV percentage=%u%% low=%u",
                        static_cast<unsigned long>(millivolts), percent, low);
    }
    else
    {
        // A failed ADC sample must not erase the last successful battery report.
        ChipLogError(AppServer, "Battery ADC sample unavailable; keeping previous reported values");
        osTimerStart(mBatteryTimer, MillisecondsToTicks(MAILBOX_BATTERY_INTERVAL_MS));
        return;
    }
#else
    ChipLogProgress(AppServer, "Battery reporting disabled: MAILBOX_BATTERY_INSTALLED=0, voltage and percentage unknown");
#endif

    PlatformMgr().LockChipStack();
    PowerSource::Attributes::Status::Set(kBatteryEndpoint,
        present ? PowerSource::PowerSourceStatusEnum::kActive : PowerSource::PowerSourceStatusEnum::kUnavailable);
    PowerSource::Attributes::BatPresent::Set(kBatteryEndpoint, present);
    PowerSource::Attributes::BatVoltage::Set(kBatteryEndpoint, voltage);
    PowerSource::Attributes::BatPercentRemaining::Set(kBatteryEndpoint, percentage);
    PowerSource::Attributes::BatReplacementNeeded::Set(kBatteryEndpoint, low);
    PowerSource::Attributes::BatChargeLevel::Set(kBatteryEndpoint,
        low ? PowerSource::BatChargeLevelEnum::kWarning : PowerSource::BatChargeLevelEnum::kOk);
    PlatformMgr().UnlockChipStack();

#if MAILBOX_BATTERY_INSTALLED
    if (osTimerStart(mBatteryTimer, MillisecondsToTicks(MAILBOX_BATTERY_INTERVAL_MS)) != osOK)
        ChipLogError(AppServer, "Failed to start daily battery timer");
#endif
}

void AppTask::PrintStatus()
{
    PlatformMgr().LockChipStack();
    const unsigned fabricCount = Server::GetInstance().GetFabricTable().FabricCount();
    const bool windowOpen = Server::GetInstance().GetCommissioningWindowManager().IsCommissioningWindowOpen();
    const bool bleEnabled = ConnectivityMgr().IsBLEAdvertisingEnabled();
    const bool bleAdvertising = ConnectivityMgr().IsBLEAdvertising();
    const unsigned bleConnections = ConnectivityMgr().NumBLEConnections();
    PlatformMgr().UnlockChipStack();
    ChipLogProgress(AppServer, "Mailbox status: sensor=%s occupancy=%u motion_count=%lu fabrics=%u INT1=%u dropped_irq=%lu battery_installed=%u window=%u ble_enabled=%u ble_advertising=%u ble_connections=%u",
                    mSensorReady ? "ready" : "unavailable", mOccupied,
                    static_cast<unsigned long>(mMotionCount), fabricCount, GPIO_PinInGet(gpioPortC, 2),
                    static_cast<unsigned long>(sDroppedInterrupts), MAILBOX_BATTERY_INSTALLED,
                    windowOpen, bleEnabled, bleAdvertising, bleConnections);
}

void AppTask::OpenCommissioningWindow()
{
    PlatformMgr().LockChipStack();
    auto & server = Server::GetInstance();
    auto & window = server.GetCommissioningWindowManager();
    if (server.GetFabricTable().FabricCount() != 0)
    {
        ChipLogError(AppServer, "Device already has a Matter fabric; use its controller to open commissioning");
    }
    else if (ConnectivityMgr().NumBLEConnections() != 0)
    {
        // Preserve any pairing session that the phone has already started.
        ChipLogProgress(AppServer, "BLE connection active; keeping the current commissioning session");
    }
    else
    {
        if (window.IsCommissioningWindowOpen())
            window.CloseCommissioningWindow();
        const CHIP_ERROR error = window.OpenBasicCommissioningWindow(System::Clock::Seconds32(900),
            CommissioningWindowAdvertisement::kAllSupported);
        if (error == CHIP_NO_ERROR)
        {
            ChipLogProgress(AppServer, "Commissioning window opened for 15 minutes");
            PrintPairingCode();
        }
        else
            ChipLogError(AppServer, "Failed to open commissioning window: %s", ErrorStr(error));
    }
    PlatformMgr().UnlockChipStack();
}

void AppTask::ButtonEventHandler(uint8_t button, uint8_t action)
{
    if (button != 0)
        return;
    AppEvent event{};
    event.Type = AppEvent::kEventType_Button;
    event.ButtonEvent.Action = action;
    event.Handler = BaseApplication::ButtonHandler;
    PostEvent(&event);
}
