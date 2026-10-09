#include "BatteryMonitor.h"

#include "em_cmu.h"
#include "em_gpio.h"
#include "em_iadc.h"
#include "sl_sleeptimer.h"
#include "sl_udelay.h"

namespace {
constexpr unsigned int kDividerEnablePin = 3; // PD3 / VBAT_CTL
constexpr unsigned int kBatteryInputPin  = 4; // PD4 / VBAT_ADC
constexpr uint32_t kReferenceMillivolts   = 1210;
constexpr uint32_t kConversionTimeoutMs  = 20;
constexpr uint32_t kSampleCount           = 8;

bool ReadSample(uint32_t & sample)
{
    const uint32_t start = sl_sleeptimer_get_tick_count();
    const uint32_t timeoutTicks = sl_sleeptimer_ms_to_tick(kConversionTimeoutMs);
    IADC_command(IADC0, iadcCmdStartSingle);
    while (IADC_getSingleFifoCnt(IADC0) == 0)
    {
        if (static_cast<uint32_t>(sl_sleeptimer_get_tick_count() - start) >= timeoutTicks)
        {
            return false;
        }
    }
    sample = IADC_pullSingleFifoResult(IADC0).data;
    return sample < 4095; // Reject a saturated converter.
}
} // namespace

bool ReadBatteryMillivolts(uint32_t & millivolts)
{
    CMU_ClockEnable(cmuClock_GPIO, true);
    GPIO_PinModeSet(gpioPortD, kDividerEnablePin, gpioModePushPull, 1);
    GPIO_PinModeSet(gpioPortD, kBatteryInputPin, gpioModeDisabled, 0);

    // U6 switches VBAT into R17/R18 (10 kohm each). Allow it to settle before
    // sampling, then turn it off again so the divider does not drain the cell.
    sl_udelay_wait(2000);

    CMU_ClockSelectSet(cmuClock_IADCCLK, cmuSelect_FSRCO);
    CMU_ClockEnable(cmuClock_IADC0, true);
    IADC_reset(IADC0);

    const uint32_t busMask = _GPIO_CDBUSALLOC_CDEVEN0_MASK;
    const uint32_t oldBus = GPIO->CDBUSALLOC & busMask;
    GPIO->CDBUSALLOC = (GPIO->CDBUSALLOC & ~busMask) | GPIO_CDBUSALLOC_CDEVEN0_ADC0;

    IADC_Init_t init = IADC_INIT_DEFAULT;
    IADC_AllConfigs_t configs = IADC_ALLCONFIGS_DEFAULT;
    IADC_InitSingle_t single = IADC_INITSINGLE_DEFAULT;
    IADC_SingleInput_t input = IADC_SINGLEINPUT_DEFAULT;

    init.srcClkPrescale = IADC_calcSrcClkPrescale(IADC0, 20000000, 0);
    configs.configs[0].reference = iadcCfgReferenceInt1V2;
    configs.configs[0].vRef = kReferenceMillivolts;
    configs.configs[0].analogGain = iadcCfgAnalogGain0P5x;
    configs.configs[0].adcClkPrescale =
        IADC_calcAdcClkPrescale(IADC0, 1000000, 0, iadcCfgModeNormal, init.srcClkPrescale);
    single.dataValidLevel = iadcFifoCfgDvl1;
    input.posInput = iadcPosInputPortDPin4;
    input.negInput = iadcNegInputGnd;
    IADC_init(IADC0, &init, &configs);
    IADC_initSingle(IADC0, &single, &input);

    // Discard the first sample after switching the analog path.
    uint32_t sample = 0;
    uint32_t sum = 0;
    bool valid = ReadSample(sample);
    for (uint32_t i = 0; valid && i < kSampleCount; ++i)
    {
        valid = ReadSample(sample);
        sum += sample;
    }

    IADC_command(IADC0, iadcCmdStopSingle);
    IADC_reset(IADC0);
    CMU_ClockEnable(cmuClock_IADC0, false);
    GPIO->CDBUSALLOC = (GPIO->CDBUSALLOC & ~busMask) | oldBus;
    GPIO_PinOutClear(gpioPortD, kDividerEnablePin);

    if (!valid)
    {
        return false;
    }

    // 0.5x IADC gain gives a 2.42 V input range; the board divider doubles
    // that to 4.84 V at VBAT. Use the internal reference so the reading still
    // works when a depleted battery pulls the board supply below 3.3 V.
    const uint32_t denominator = kSampleCount * 4095;
    const uint32_t measured = (sum * (4 * kReferenceMillivolts) + denominator / 2) / denominator;
    if (measured < 2200 || measured > 4500)
    {
        return false;
    }
    millivolts = measured;
    return true;
}
