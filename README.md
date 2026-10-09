# Matter Over Thread End Sleepy Device With BLE Commissioning

Implements a motion sensor with a Silicon Labs MG24 MCU and a Bosch BMA400 IMU - be notified when the mailman delivers your mail by attaching an accelerometer to the mailbox lid. This code puts together all the bits that seem to be required for a Matter over Thread End Sleepy Device (ESD) with BLE commissioning.

## Power Consumption

Power consumption is to be measured shortly.

<!-- This setup seems to average ???µA at 4V from the battery when idling. The idle power draw is ok but not great. -->

## Requirements

* A custom PCB based on the XIAO MG24 and the BMA400 accelerometer. The design is [here](hw/board).
* A LiPo battery with a JST PH 2.0 connector.

Alternatively, you can cobble together your own setup.

## Downloading the Firmware

### Dependencies

Install OpenOCD with MG24 support to be able to flash the board.

### Download

Download the latest released [firmware](https://github.com/retsyx/amity/releases/latest/download/MailboxMotion.zip). Unzip it.

From this project directory. Find the device serial number:

```sh
python3 scripts/find-serial.py
```

Flash the HEX file:

```sh
python3 scripts/flash.py --serial <serial> --image <path to extracted HEX file>
```

## Building

### Dependencies

* Simplicity SDK must be installed with Matter support and in PATH so that the `slt` command is invocable.
* OpenOCD with MG24 support.

### Build

Run from this project directory:

```sh
python3 scripts/build.py
```

To run the automated tests:

```sh
python3 scripts/test-driver.py
```


Useful build options:

```sh
python3 scripts/build.py --console
python3 scripts/build.py --battery
python3 scripts/build.py --console --battery
python3 scripts/build.py --generate
```

The default profile disables the USB UART initializer, leaves PA8/PA9 disconnected, omits the Matter shell and Thread CLI, keeps the application status LED off, and disables EM2 debugging. It also removes SWD routing and its pulls after a **five-second startup recovery window**; a later debugger connection requires the physical XIAO reset switch or a power cycle, followed by connection during that window.

* `--console` restores USB UART, the shell, Thread CLI, status LEDs and EM2 debugging, and keeps SWD available. UART reception holds the MCU in EM1 or a more active mode, so use this profile for diagnostics rather than battery-current comparisons.
* `--battery` enables reporting for a battery that has actually been fitted. Without it, the charger output is never interpreted as evidence of a battery.

The build produces `build/MailboxMotion` (ELF), `build/MailboxMotion.hex`, `build/MailboxMotion.bin`, and a linker map.

Silicon Labs platform files are genereated from [MailboxMotion.slcp](MailboxMotion.slcp) and the maintained `config/` inputs using Studio's bundled SLC. The Matter data model is generated from [mailbox-motion.zap](config/common/mailbox-motion.zap) with ZAP.

## Flashing and Monitoring

If the running default image has already released SWD, press the **physical XIAO reset switch** or power-cycle the board immediately before starting the upload, so the debugger connects within five seconds. Automatic hardware reset through the USB bridge was tested and did not reset this target; the uploader does not provide automatic connect-under-reset recovery. Once installed, an image installed with the `--console` option keeps SWD available.

Find the CMSIS-DAP serial number for attached devices on macOS or Linux:

```sh
python3 scripts/find-serial.py
```

Check that all required tools are available for flashing:

```sh
python3 scripts/flash.py --check-tools
```


Flash using the CMSIS-DAP serial that was found earlier:

```sh
python3 scripts/flash.py --serial <serial>
```

Optionally monitor the device.

On MacOS:

```sh
python3 scripts/monitor.py --port /dev/cu.usbmodem<serial>
```

On Linux:

```sh
python3 scripts/monitor.py --port /dev/serial/by-id/*<serial>*
```

## Matter Commissioning

An uncommissioned device opens a **15-minute commissioning window at boot**. With a console build, `mailbox commission` also reopens it for 15 minutes. The command preserves active BLE pairing sessions and refuses to reopen a device that already has a Matter fabric. Resetting the MCU preserves its fabric and does not factory-reset the accessory.

With your favorite Matter commissioner (HomeKit, etc.) add the accessory.

This project uses development commissioning credentials, so the QR code is always the one below.

![matter provisioning QR code](matter_qr.png)

Commissioning values use the defaults in [CHIPProjectConfig.h](include/CHIPProjectConfig.h):

| Setting | Value |
| --- | --- |
| Manual pairing code | `34970112332` |
| Setup passcode | `20202021` |
| Long discriminator | `3840` / `0xF00` |
| Vendor ID | `0xFFF1` |
| Product ID | `0x8004` |

## Details

### Serial Diagnostics

With `--console`, the application uses the XIAO's USB serial bridge at **115200 baud, 8 data bits, no parity, one stop bit**. The application UART is EUSART0 on PA8/PA9. The default profile leaves those pins disconnected and supplies no UART shell or output; see [hardware details](docs/hardware.md#usb-serial-and-board-controls).

At the Matter shell prompt:

```text
mailbox status
mailbox motion
mailbox battery
mailbox commission
```

* `status` prints sensor availability, occupancy, motion and fabric counts, INT1 level, dropped GPIO interrupts, battery configuration, and BLE/commissioning state.
* `motion` injects one test indication through the application queue and five-second timer. It verifies the application path without a connected accelerometer.
* `battery` requests an immediate battery attribute update; values remain unknown in the default build.
* `commission` queues a request to reopen commissioning on an uncommissioned device.


### BMA400 Motion configuration

[Bma400Motion.cpp](src/bma400/Bma400Motion.cpp) applies the followsing sensor configuration:

| Setting | Value |
| --- | --- |
| Resting power mode | Low power |
| Wake-up axes | X, Y, Z |
| Wake-up reference update | One time after initialization |
| Wake-up sample count | 8 |
| Wake-up threshold | Register value 4 |
| Wake-up reference X / Y / Z | 255 / 255 / 255 |
| Wake-up output | INT1, push-pull, active high |
| Automatic low-power timeout | 400 units, approximately one second |
| Generic interrupt 2 | Activity on any axis; threshold 5; duration 1 |
| Generic interrupt 2 data / reference | Filter 2; update reference every time |
| Generic interrupt 2 hysteresis | 48 mg |
| Generic interrupt 2 reference X / Y / Z | 0 / 0 / 512 |


### Antenna Selection

Before starting BLE or Thread, [main.cpp](src/main.cpp) drives **PB5 high** to power the RF switch and **PB4 low** to select the onboard antenna. See Seeed's [antenna-selection instructions](https://wiki.seeedstudio.com/xiao_mg24_bluetooth/#switching-between-built-in-and-external-antennas). The application also switches off the optional Sense IMU supply on PD5 and microphone enable on PC8, keeps the battery divider off until sampling, and sends the unused onboard Puya flash a deep-power-down command. The RF switch remains powered for radio operation.

### Board Clocks

The native clock configuration uses the XIAO's crystals and load settings:

| Clock setting | Value |
| --- | --- |
| HFXO frequency / CTUNE | 39 MHz / 95 |
| LFXO frequency / CTUNE | 32.768 kHz / 44 |
| LFXO enabled | Yes |
| Default low-frequency clock source | LFXO |

These values are configured in [sl_clock_manager_oscillator_config.h](config/sl_clock_manager_oscillator_config.h) and [sl_clock_manager_tree_config.h](config/sl_clock_manager_tree_config.h). The Silicon Labs-authored [upstream XIAO MG24 board definition](https://github.com/zephyrproject-rtos/zephyr/blob/main/boards/seeed/xiao_mg24/xiao_mg24.dts) supplies the board-specific crystal settings.

### Battery Measurement

The XIAO MG24 has an onboard switched battery divider. **PD3 enables it; PD4 measures its midpoint.** The schematic specifies equal 10 kΩ resistors, so VBAT is twice the sensed voltage. [BatteryMonitor.cpp](../src/BatteryMonitor.cpp) enables the path, allows it to settle, samples IADC0 using the internal reference, and disables the path afterwards. See the [power circuit in the Seeed schematic](https://files.seeedstudio.com/wiki/XIAO_MG24/Getting_Start/XIAO_MG24_SCH.pdf).

Enable reporting with `python3 scripts/build.py --battery` only when a rechargeable battery is fitted. A voltage at VBAT does not prove that a cell is attached: USB powers the charger circuit. The default reports unknown voltage and percentage with battery presence false.

The estimate maps 3.5 V to 0% and 4.2 V to 100%, with low-battery indication below 20%.
