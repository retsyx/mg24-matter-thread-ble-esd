// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stdint.h>

#include "bma400.h"
#include "sl_i2cspm.h"

// Native Silicon Labs transport for the mailbox's external BMA400.
// The caller initializes I2CSPM and the sleeptimer before calling begin(),
// and owns retry timing. Call these methods from task context, never an ISR.
class Bma400Motion
{
public:
    int8_t begin(I2C_TypeDef *bus, uint8_t address = BMA400_I2C_ADDRESS_SDO_LOW);
    int8_t readInterruptStatus(uint16_t &status);
    // Raw signed acceleration values; the reset range is +/-4 g.
    int8_t readSample(bma400_sensor_data &sample);
    bool initialized() const { return mInitialized; }
    uint8_t chipId() const { return mDevice.chip_id; }

    // intf_ptr refers to this object; copying it would invalidate that link.
    Bma400Motion() = default;
    Bma400Motion(const Bma400Motion &) = delete;
    Bma400Motion &operator=(const Bma400Motion &) = delete;

private:
    int8_t configureMotion();
    static BMA400_INTF_RET_TYPE readRegisters(uint8_t reg, uint8_t *data,
                                            uint32_t length, void *context);
    static BMA400_INTF_RET_TYPE writeRegisters(uint8_t reg, const uint8_t *data,
                                             uint32_t length, void *context);
    static void delayMicroseconds(uint32_t period, void *context);

    bma400_dev mDevice = {};
    I2C_TypeDef *mBus = nullptr;
    uint8_t mAddress = BMA400_I2C_ADDRESS_SDO_LOW;
    bool mInitialized = false;
};
