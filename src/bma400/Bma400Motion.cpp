// SPDX-License-Identifier: GPL-3.0-or-later
#include "Bma400Motion.h"

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

    // Nonlatching is the reset default; state it explicitly to keep INT1
    // behavior predictable. Motion automatically changes low-power to normal.
    bma400_int_enable interrupts[2] = {};
    interrupts[0].type = BMA400_LATCH_INT_EN;
    interrupts[0].conf = BMA400_DISABLE;
    interrupts[1].type = BMA400_AUTO_WAKEUP_EN;
    interrupts[1].conf = BMA400_ENABLE;
    status = bma400_enable_interrupt(interrupts, 2, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }

    bma400_device_conf lowPower = {};
    lowPower.type = BMA400_AUTO_LOW_POWER;
    lowPower.param.auto_lp.auto_low_power_trigger = BMA400_AUTO_LP_TIME_RESET_EN;
    lowPower.param.auto_lp.auto_lp_timeout_threshold = 400; // 400 * 2.5 ms = 1 s
    status = bma400_set_device_conf(&lowPower, 1, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }

    // GEN2 resets the one-second low-power timer while the lid keeps moving.
    // It is deliberately unmapped, so only the wakeup condition drives INT1.
    bma400_sensor_conf generic = {};
    generic.type = BMA400_GEN2_INT;
    generic.param.gen_int.gen_int_thres = 5;
    generic.param.gen_int.gen_int_dur = 1;
    generic.param.gen_int.axes_sel = BMA400_AXIS_XYZ_EN;
    generic.param.gen_int.data_src = BMA400_DATA_SRC_ACCEL_FILT_2;
    generic.param.gen_int.criterion_sel = BMA400_ACTIVITY_INT;
    generic.param.gen_int.evaluate_axes = BMA400_ANY_AXES_INT;
    generic.param.gen_int.ref_update = BMA400_UPDATE_EVERY_TIME;
    generic.param.gen_int.hysteresis = BMA400_HYST_48_MG;
    generic.param.gen_int.int_thres_ref_x = 0;
    generic.param.gen_int.int_thres_ref_y = 0;
    generic.param.gen_int.int_thres_ref_z = 512;
    generic.param.gen_int.int_chan = BMA400_UNMAP_INT_PIN;
    status = bma400_set_sensor_conf(&generic, 1, &mDevice);
    if (status != BMA400_OK)
    {
        return status;
    }

    bma400_int_enable genericEnable = {};
    genericEnable.type = BMA400_GEN2_INT_EN;
    genericEnable.conf = BMA400_ENABLE;
    status = bma400_enable_interrupt(&genericEnable, 1, &mDevice);
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
    // Bosch requests minimum delays. Round upwards to the native sleeptimer's
    // millisecond resolution, including its submillisecond register delays.
    uint32_t milliseconds = period / 1000 + (period % 1000 != 0);
    while (milliseconds != 0)
    {
        const uint16_t chunk = milliseconds > UINT16_MAX ? UINT16_MAX : static_cast<uint16_t>(milliseconds);
        sl_sleeptimer_delay_millisecond(chunk);
        milliseconds -= chunk;
    }
}
