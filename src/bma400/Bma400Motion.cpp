// SPDX-License-Identifier: GPL-3.0-or-later
#include "Bma400Motion.h"

#include "cmsis_os2.h"
#include "sl_sleeptimer.h"

int8_t Bma400Motion::begin(I2C_TypeDef *bus, uint8_t address)
{
    mInitialized = false;
    if (bus == nullptr)
    {
        return BMA400_E_NULL_PTR;
    }
    if (address != BMA400_I2C_ADDRESS_SDO_LOW && address != BMA400_I2C_ADDRESS_SDO_HIGH)
    {
        return BMA400_E_INVALID_CONFIG;
    }

    mBus = bus;
    mAddress = address;
    mDevice = {};
    mDevice.intf = BMA400_I2C_INTF;
    mDevice.intf_ptr = this;
    mDevice.read = readRegisters;
    mDevice.write = writeRegisters;
    mDevice.delay_us = delayMicroseconds;

    int8_t status = bma400_soft_reset(&mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }
    status = bma400_init(&mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }
    status = bma400_set_power_mode(BMA400_MODE_NORMAL, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }
    status = configureMotion();
    mInitialized = (status == BMA400_OK);
    return status;
}

int8_t Bma400Motion::configureMotion()
{
    // Reset defaults provide low-power OSR0, fixed 25 Hz low-power sampling,
    // and a +/-4 g range.
    bma400_device_conf wakeup = {};
    wakeup.type = BMA400_AUTOWAKEUP_INT;
    wakeup.param.wakeup.wakeup_ref_update = BMA400_UPDATE_ONE_TIME;
    wakeup.param.wakeup.sample_count = BMA400_SAMPLE_COUNT_8;
    wakeup.param.wakeup.wakeup_axes_en = BMA400_AXIS_XYZ_EN;
    wakeup.param.wakeup.int_wkup_threshold = 4;
    wakeup.param.wakeup.int_wkup_ref_x = 255;
    wakeup.param.wakeup.int_wkup_ref_y = 255;
    wakeup.param.wakeup.int_wkup_ref_z = 255;
    wakeup.param.wakeup.int_chan = BMA400_INT_CHANNEL_1;
    int8_t status = bma400_set_device_conf(&wakeup, 1, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }

    bma400_device_conf pin = {};
    pin.type = BMA400_INT_PIN_CONF;
    pin.param.int_conf.int_chan = BMA400_INT_CHANNEL_1;
    pin.param.int_conf.pin_conf = BMA400_INT_PUSH_PULL_ACTIVE_1;
    status = bma400_set_device_conf(&pin, 1, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }

    // The wakeup detector always runs in low-power mode and can drive INT1
    // independently of auto-wakeup (Bosch datasheet, p. 21). Keep the sensor
    // in low power during motion; AppTask resets it after the five-second
    // occupancy pulse to capture a fresh one-time reference.
    bma400_int_enable interrupts[2] = {};
    interrupts[0].type = BMA400_LATCH_INT_EN;
    interrupts[0].conf = BMA400_DISABLE;
    interrupts[1].type = BMA400_AUTO_WAKEUP_EN;
    interrupts[1].conf = BMA400_DISABLE;
    status = bma400_enable_interrupt(interrupts, 2, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }

    // FIFO_PWR_CONFIG.fifo_read_disable saves 100 nA. The application reads
    // only acceleration/status registers, so no FIFO read circuit is needed.
    // Apply after every soft reset; the other bits in this register are reserved.
    const uint8_t fifoReadDisable = 0x01;
    status = bma400_set_regs(BMA400_REG_FIFO_READ_EN, &fifoReadDisable, 1, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }
    return bma400_set_power_mode(BMA400_MODE_LOW_POWER, &mDevice);
}

int8_t Bma400Motion::readInterruptStatus(uint16_t &status)
{
    status = 0;
    if (!mInitialized)
    {
        return BMA400_E_DEV_NOT_FOUND;
    }
    return bma400_get_interrupt_status(&status, &mDevice);
}

int8_t Bma400Motion::readSample(bma400_sensor_data &sample)
{
    sample = {};
    if (!mInitialized)
    {
        return BMA400_E_DEV_NOT_FOUND;
    }
    return bma400_get_accel_data(BMA400_DATA_ONLY, &sample, &mDevice);
}

BMA400_INTF_RET_TYPE Bma400Motion::readRegisters(uint8_t reg, uint8_t *data,
                                               uint32_t length, void *context)
{
    auto *self = static_cast<Bma400Motion *>(context);
    if (self == nullptr || self->mBus == nullptr || data == nullptr || length == 0 || length > UINT16_MAX)
    {
        return BMA400_E_COM_FAIL;
    }
    I2C_TransferSeq_TypeDef sequence = {};
    sequence.addr = static_cast<uint16_t>(self->mAddress << 1);
    sequence.flags = I2C_FLAG_WRITE_READ;
    sequence.buf[0].data = &reg;
    sequence.buf[0].len = 1;
    sequence.buf[1].data = data;
    sequence.buf[1].len = static_cast<uint16_t>(length);
    // I2CSPM reports Done only after the complete specified transfer succeeds.
    return I2CSPM_Transfer(self->mBus, &sequence) == i2cTransferDone ? BMA400_INTF_RET_SUCCESS : BMA400_E_COM_FAIL;
}

BMA400_INTF_RET_TYPE Bma400Motion::writeRegisters(uint8_t reg, const uint8_t *data,
                                                uint32_t length, void *context)
{
    auto *self = static_cast<Bma400Motion *>(context);
    if (self == nullptr || self->mBus == nullptr || data == nullptr || length == 0 || length > UINT16_MAX)
    {
        return BMA400_E_COM_FAIL;
    }
    I2C_TransferSeq_TypeDef sequence = {};
    sequence.addr = static_cast<uint16_t>(self->mAddress << 1);
    sequence.flags = I2C_FLAG_WRITE_WRITE;
    sequence.buf[0].data = &reg;
    sequence.buf[0].len = 1;
    // EMLIB uses one pointer type for both directions. WRITE_WRITE reads it.
    sequence.buf[1].data = const_cast<uint8_t *>(data);
    sequence.buf[1].len = static_cast<uint16_t>(length);
    return I2CSPM_Transfer(self->mBus, &sequence) == i2cTransferDone ? BMA400_INTF_RET_SUCCESS : BMA400_E_COM_FAIL;
}

void Bma400Motion::delayMicroseconds(uint32_t period, void *)
{
    if (period == 0)
    {
        return;
    }
    if (osKernelGetState() == osKernelRunning)
    {
        const uint32_t frequency = osKernelGetTickFreq();
        // Release the application task during reset/mode settling. A relative
        // RTOS delay can lose almost one tick to the current tick's phase, so
        // add a tick after rounding up to preserve Bosch's minimum delay.
        const uint64_t ticks = (static_cast<uint64_t>(period) * frequency + 999999u) / 1000000u + 1u;
        if (frequency != 0 && ticks < UINT32_MAX && osDelay(static_cast<uint32_t>(ticks)) == osOK)
        {
            return;
        }
    }

    // Before the scheduler starts (or if it cannot block), keep the original
    // sleeptimer fallback and round upwards to its millisecond resolution.
    uint32_t milliseconds = period / 1000 + (period % 1000 != 0);
    while (milliseconds != 0)
    {
        const uint16_t chunk = milliseconds > UINT16_MAX ? UINT16_MAX : static_cast<uint16_t>(milliseconds);
        sl_sleeptimer_delay_millisecond(chunk);
        milliseconds -= chunk;
    }
}
