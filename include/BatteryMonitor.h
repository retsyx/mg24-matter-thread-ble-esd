#pragma once

#include <stdint.h>

// Read the XIAO MG24 VBAT node through its switched 1:2 divider.
// Call from one application task after the Silicon Labs platform initializes.
// This helper owns IADC0; do not use another IADC0 client concurrently.
// Returns false for a failed conversion or a voltage outside 2.2–4.5 V and
// leaves millivolts unchanged. A valid voltage does not prove a cell is fitted:
// the onboard charger can energize VBAT while USB powers the board.
bool ReadBatteryMillivolts(uint32_t & millivolts);
