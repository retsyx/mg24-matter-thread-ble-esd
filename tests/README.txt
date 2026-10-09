Run: python3 scripts/test-driver.py

Requires Python 3 and an already-installed host C/C++ compiler. CC/CXX may
override compiler commands. The script installs nothing and builds only in a
temporary directory, removed afterwards.

This test compiles the real Bma400Motion wrapper and Bosch SensorAPI against
mocked native Silicon Labs I2CSPM and sleeptimer declarations. It checks bus
addressing, initialization configuration, injected NACKs at every init transfer,
no hidden retries, chip identity, signed samples, and failed interrupt reads.
It also checks that interrupt reads introduce no sleeptimer delays.

The mock checks software behavior only. It does not establish hardware wiring,
physical interrupt timing, sensor motion response, MCU power consumption,
Matter commissioning, or compatibility with an actual Silicon Labs SDK. Those
require the firmware build and board validation described in the project docs.
The native_stubs directory is outside the firmware include paths.
