// Host test stand-in; delays are checked but do not sleep.
#pragma once

#include <stdint.h>

void sl_sleeptimer_delay_millisecond(uint16_t milliseconds);
