#!/usr/bin/env python3
"""Flash native MG24 HEX through CMSIS-DAP using installed OpenOCD."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

# OpenOCD must support the MG24 which at the time of this writing may not be the default.
# On MacOS you may need to install openocd like so:
# brew unlink open-ocd
# brew install --HEAD open-ocd

def find_openocd():
    executable = shutil.which('openocd')
    if not executable:
        raise SystemExit('OpenOCD not found on PATH. Install openOCD.')
    return executable


def tcl_path(p):
    p = str(p.resolve())
    if any(c in p for c in '{}\n\r'):
        raise SystemExit('Unsupported characters in file path')
    return '{' + p + '}'


def run_openocd(command):
    connection_failed = False
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, errors='replace') as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                if 'error connecting dp' in line.lower() or 'cannot read idr' in line.lower():
                    connection_failed = True
            returncode = process.wait()
    except OSError as error:
        raise SystemExit(f'Could not start OpenOCD: {error}') from None
    if returncode:
        if connection_failed:
            raise SystemExit(
                'Could not connect to the MG24 over SWD. The running firmware may have disabled SWD.\n'
                'Press the physical reset button on the XIAO board, then immediately rerun '
                'this command (within five seconds of reset).')
        raise SystemExit(f'OpenOCD failed (exit code {returncode}). See its output above for details.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', help='CMSIS-DAP serial number, e.g. C904F413')
    parser.add_argument('--image', type=Path, default=ROOT / 'build/MailboxMotion.hex')
    parser.add_argument('--backup-only', action='store_true')
    parser.add_argument('--check-tools', action='store_true',
                        help='check OpenOCD and target configuration without connecting to hardware')
    args = parser.parse_args()
    if not args.check_tools and not args.serial:
        parser.error('--serial is required for flashing or backup')
    if args.serial and not args.serial.isalnum():
        parser.error('Expected an alphanumeric CMSIS-DAP serial number')
    if not args.check_tools and not args.backup_only and (
            not args.image.is_file() or args.image.suffix.lower() != '.hex'):
        raise SystemExit('Build native firmware first; expected a HEX image')
    executable = find_openocd()
    target = 'target/silabs/xg24.cfg'
    print('OpenOCD: ' + executable, flush=True)
    print('Target: ' + target, flush=True)
    base = [executable, '-f', 'interface/cmsis-dap.cfg',
            '-c', 'transport select swd']
    if args.serial:
        base += ['-c', 'adapter serial ' + args.serial]
    base += ['-f', target, '-c', 'gdb port disabled; tcl port disabled; telnet port disabled']
    if args.check_tools:
        run_openocd(base + ['-c', 'shutdown'])
        return
    backup = ROOT / 'build/backups' / (args.serial + '-before-mailbox.bin')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        run_openocd(base + ['-c', 'init; reset halt; dump_image ' + tcl_path(backup) +
                           ' 0x08000000 0x180000; reset run; shutdown'])
    if not backup.is_file() or backup.stat().st_size != 1536 * 1024:
        raise SystemExit('Flash backup is incomplete; refusing to program')
    if not args.backup_only:
        run_openocd(base + ['-c', 'program ' + tcl_path(args.image) + ' verify reset exit'])
    print('Flash backup: ' + str(backup))


if __name__ == '__main__':
    main()
