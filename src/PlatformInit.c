// SPDX-License-Identifier: GPL-3.0-or-later
// Project-specific initialization policy, independent of SLC-generated code.

#include "em_cmu.h"
#include "em_gpio.h"
#include "sl_uartdrv_eusart_vcom_config.h"

void __real_sl_uartdrv_init_instances(void);

// The generated driver initializer calls this through GNU ld's --wrap option.
void __wrap_sl_uartdrv_init_instances(void)
{
#if MAILBOX_CONSOLE_KEEP_AWAKE
  __real_sl_uartdrv_init_instances();
#else
  // The USB-only SAMD11 bridge is unpowered on VBAT. Keep its UART signals
  // high impedance and leave the UART driver uninitialized.
  CMU_ClockEnable(cmuClock_GPIO, true);
  GPIO_PinModeSet((GPIO_Port_TypeDef)SL_UARTDRV_EUSART_VCOM_TX_PORT,
                  SL_UARTDRV_EUSART_VCOM_TX_PIN, gpioModeDisabled, 0);
  GPIO_PinModeSet((GPIO_Port_TypeDef)SL_UARTDRV_EUSART_VCOM_RX_PORT,
                  SL_UARTDRV_EUSART_VCOM_RX_PIN, gpioModeDisabled, 0);
#endif
}
