#!/usr/bin/env python3
"""Build with existing native Silicon Labs packages. Never installs tools."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

from silabs_tools import executable, package

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--battery', action='store_true', help='a LiPo is fitted; enable battery reports')
parser.add_argument('--console', action='store_true', help='enable USB UART, shell, Thread CLI and EM2 debugging; keeps reception in EM1 (default: production with UART pins disconnected and RTT logging)')
parser.add_argument('--radio-gated-switch', action=argparse.BooleanOptionalAction, default=True,
                    help='power the antenna switch from radio-active PRS (default: enabled); --no-radio-gated-switch keeps it powered for comparison')
parser.add_argument('--generate', action='store_true', help='force platform and Matter regeneration (normal builds generate automatically)')
parser.add_argument('-j', '--jobs', type=int, default=min(os.cpu_count() or 4, 8))
args = parser.parse_args()
slt = shutil.which('slt')
if not slt:
    raise SystemExit('Silicon Labs Tool (slt) not found on PATH. Add the SLT executable directory to PATH.')
sdk = package(slt, 'simplicity-sdk', '2025.6.2')
matter = package(slt, 'matter_extension', '2.7.0')
gcc = package(slt, 'gcc-arm-none-eabi', '12.2.rel1')
gcc_executable = executable(gcc, 'arm-none-eabi-gcc', slt, 'gcc-arm-none-eabi/12.2.rel1')
cmake = executable(package(slt, 'cmake', '3.30.2'), 'cmake', slt, 'cmake/3.30.2')
ninja = executable(package(slt, 'ninja', '1.12.1'), 'ninja', slt, 'ninja/1.12.1')
zap = package(slt, 'zap', '2026.08.24')
zap_cli = executable(zap, 'zap-cli', slt, 'zap/2026.08.24')
slc = executable(package(slt, 'slc-cli', '6.0.22'), 'slc', slt, 'slc-cli/6.0.22')
java = executable(package(slt, 'java21', '21.0.6'), 'java', slt, 'java21/21.0.6')
silabs_python = package(slt, 'python', '3.10.3')
python = executable(silabs_python, 'python', slt, 'python/3.10.3')
if args.generate:
    (ROOT / 'build/slc/autogen/.generation.stamp').unlink(missing_ok=True)
env = dict(os.environ, ARM_GCC_DIR=str(gcc),
           PATH=os.pathsep.join(map(str, (python.parent, java.parent, gcc_executable.parent,
                                        cmake.parent, ninja.parent, zap_cli.parent, slc.parent)))
                + os.pathsep + os.environ.get('PATH', ''))
subprocess.run([str(cmake), '-S', str(ROOT / 'cmake_gcc'), '-B', str(ROOT / 'build'), '-G', 'Ninja',
                '-DCMAKE_TOOLCHAIN_FILE=' + str(ROOT / 'cmake_gcc/toolchain.cmake'),
                '-DCMAKE_MAKE_PROGRAM=' + str(ninja), '-DSDK_PATH=' + str(sdk),
                '-DMATTER_PATH=' + str(matter),
                '-DZAP_PATH=' + str(zap), '-DZAP_CLI=' + str(zap_cli),
                '-DSLC_CLI=' + str(slc), '-DJAVA_EXECUTABLE=' + str(java),
                '-DSILABS_PYTHON_PATH=' + str(silabs_python),
                '-DSILABS_PYTHON_EXECUTABLE=' + str(python),
                '-DGCC_PATH=' + str(gcc), '-DGCC_EXECUTABLE=' + str(gcc_executable),
                '-DMAILBOX_BATTERY_INSTALLED=' + ('ON' if args.battery else 'OFF'),
                '-DMAILBOX_CONSOLE_KEEP_AWAKE=' + ('ON' if args.console else 'OFF'),
                '-DMAILBOX_RADIO_GATED_SWITCH=' + ('ON' if args.radio_gated_switch else 'OFF'),
                '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], env=env, check=True)
subprocess.run([str(cmake), '--build', str(ROOT / 'build'), '-j', str(args.jobs)], env=env, check=True)
