// Host test stand-in for the native SDK declarations used by Bma400Motion.
// This header is never included in the firmware build.
#pragma once

#include <stdint.h>

struct I2C_TypeDef
{};

struct I2C_TransferSeq_TypeDef
{
    uint16_t addr;
    uint16_t flags;
    struct
    {
        uint8_t *data;
        uint16_t len;
    } buf[2];
};

enum I2C_TransferReturn_TypeDef
{
    i2cTransferDone = 0,
    i2cTransferNack = -1
};

#define I2C_FLAG_WRITE_READ 4
#define I2C_FLAG_WRITE_WRITE 8

I2C_TransferReturn_TypeDef I2CSPM_Transfer(I2C_TypeDef *bus, I2C_TransferSeq_TypeDef *sequence);
