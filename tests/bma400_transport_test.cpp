// SPDX-License-Identifier: GPL-3.0-or-later
// Runs the actual driver and Bosch API against a mocked native I2CSPM bus.
#include <cassert>
#include <cstdio>
#include <cstring>

#include "Bma400Motion.h"

namespace
{
uint8_t registers[256];
bool nack = false;
bool wrongChip = false;
unsigned transfers = 0;
unsigned failAtTransfer = 0;
unsigned delays = 0;
uint8_t expectedAddress = 0x14;
I2C_TypeDef *expectedBus = nullptr;

void resetRegisters()
{
    memset(registers, 0, sizeof(registers));
    registers[0] = wrongChip ? 0 : 0x90;
    registers[0x1A] = 0x49; // BMA400 reset value: +/-4 g, normal ODR 200 Hz.
}

void checkConfiguration()
{
    assert(registers[0x19] == 0x01); // Low-power mode, OSR0.
    assert(registers[0x1A] == 0x49); // Normal sampling/range defaults preserved.
    assert(registers[0x2F] == 0xFD); // XYZ, 8 samples, one-time reference.
    assert(registers[0x30] == 4);
    assert(registers[0x31] == 255 && registers[0x32] == 255 && registers[0x33] == 255);
    assert(registers[0x24] == 0x02); // INT1 active-high push/pull.
    assert(registers[0x2A] == 25 && registers[0x2B] == 8); // One-second auto LP.
    assert(registers[0x2D] == 2); // Auto wakeup enabled.
    assert(registers[0x1F] == 8 && registers[0x20] == 0); // GEN2, nonlatching.
}
} // namespace

void sl_sleeptimer_delay_millisecond(uint16_t milliseconds)
{
    assert(milliseconds != 0);
    ++delays;
}

I2C_TransferReturn_TypeDef I2CSPM_Transfer(I2C_TypeDef *bus, I2C_TransferSeq_TypeDef *sequence)
{
    ++transfers;
    assert(bus == expectedBus);
    assert(sequence->addr == (expectedAddress << 1)); // Native 8-bit address format.
    assert(sequence->buf[0].len == 1);
    if (nack || (failAtTransfer != 0 && transfers == failAtTransfer))
    {
        return i2cTransferNack;
    }

    const uint8_t reg = sequence->buf[0].data[0];
    assert(reg + sequence->buf[1].len <= sizeof(registers));
    if (sequence->flags == I2C_FLAG_WRITE_READ)
    {
        assert(sequence->buf[1].len != 0);
        memcpy(sequence->buf[1].data, &registers[reg], sequence->buf[1].len);
    }
    else
    {
        assert(sequence->flags == I2C_FLAG_WRITE_WRITE);
        assert(sequence->buf[1].len == 1); // Bosch splits unsupported burst writes.
        if (reg == 0x7E && sequence->buf[1].data[0] == 0xB6)
        {
            resetRegisters();
        }
        else
        {
            memcpy(&registers[reg], sequence->buf[1].data, sequence->buf[1].len);
        }
    }
    return i2cTransferDone;
}

int main()
{
    I2C_TypeDef bus;
    expectedBus = &bus;
    Bma400Motion sensor;
    uint16_t status = 123;
    assert(sensor.readInterruptStatus(status) == BMA400_E_DEV_NOT_FOUND && status == 0);
    assert(sensor.begin(nullptr) == BMA400_E_NULL_PTR);
    assert(sensor.begin(&bus, 0x16) == BMA400_E_INVALID_CONFIG && transfers == 0);

    nack = true;
    assert(sensor.begin(&bus) == BMA400_E_COM_FAIL && !sensor.initialized() && transfers == 1);
    nack = false;
    transfers = 0;
    assert(sensor.begin(&bus) == BMA400_OK && sensor.initialized() && sensor.chipId() == 0x90);
    assert(delays != 0);
    checkConfiguration();
    const unsigned successfulInitTransfers = transfers;

    // A disconnected sensor must abort initialization at every possible bus
    // operation. Partial configuration must never be marked ready or retried.
    for (unsigned failure = 1; failure <= successfulInitTransfers; ++failure)
    {
        transfers = 0;
        failAtTransfer = failure;
        assert(sensor.begin(&bus) == BMA400_E_COM_FAIL);
        assert(!sensor.initialized() && transfers == failure);
    }
    failAtTransfer = 0;
    assert(sensor.begin(&bus) == BMA400_OK && sensor.initialized());

    registers[0x0E] = 1;
    const unsigned delaysBeforeStatus = delays;
    assert(sensor.readInterruptStatus(status) == BMA400_OK && status == BMA400_ASSERTED_WAKEUP_INT);
    assert(delays == delaysBeforeStatus); // IRQ servicing does not incur driver delays.

    // Positive and negative signed 12-bit acceleration boundaries.
    const uint8_t sampleRegisters[] = { 0xFF, 0x07, 0x00, 0x08, 0xFF, 0x0F };
    memcpy(&registers[0x04], sampleRegisters, sizeof(sampleRegisters));
    bma400_sensor_data sample;
    assert(sensor.readSample(sample) == BMA400_OK);
    assert(sample.x == 2047 && sample.y == -2048 && sample.z == -1);

    // Regression: Bosch v1.5.8 decoded an uninitialized buffer on a failed
    // status read. The application must receive zero plus the I2C error.
    nack = true;
    status = 123;
    const unsigned beforeFailure = transfers;
    assert(sensor.readInterruptStatus(status) == BMA400_E_COM_FAIL);
    assert(status == 0 && transfers == beforeFailure + 1);
    assert(sensor.readSample(sample) == BMA400_E_COM_FAIL);
    assert(sample.x == 0 && sample.y == 0 && sample.z == 0);
    nack = false;

    wrongChip = true;
    assert(sensor.begin(&bus) == BMA400_E_DEV_NOT_FOUND && !sensor.initialized());
    wrongChip = false;

    // Both documented SDO strap addresses are accepted and shifted correctly.
    expectedAddress = 0x15;
    assert(sensor.begin(&bus, expectedAddress) == BMA400_OK && sensor.initialized());
    checkConfiguration();
    puts("BMA400 mocked native transport regression checks passed");
}
