#!/usr/bin/env python3
"""List CMSIS-DAP USB probe serial numbers on macOS and Linux."""
import argparse
from dataclasses import dataclass
from pathlib import Path
import plistlib
import re
import subprocess
import sys


@dataclass
class Probe:
    serial: str
    product: str
    vendor: int
    device: int


def is_cmsis_dap(vendor, device, names):
    # The XIAO bridge's product descriptor may omit CMSIS-DAP.
    if (vendor, device) == (0x2886, 0x0062):
        return True
    return any('cmsisdap' in re.sub(r'[^a-z0-9]', '', name.lower())
               or 'daplink' in name.lower() for name in names)


def registry_entries(node):
    if isinstance(node, list):
        for child in node:
            yield from registry_entries(child)
    elif isinstance(node, dict):
        yield node
        yield from registry_entries(node.get('IORegistryEntryChildren', []))


def macos_probes(registry):
    probes = []
    for node in registry_entries(registry):
        vendor, device = node.get('idVendor'), node.get('idProduct')
        if not isinstance(vendor, int) or not isinstance(device, int):
            continue
        product = node.get('USB Product Name') or node.get('IORegistryEntryName', '')
        names = [product, node.get('IORegistryEntryName', '')]
        # Match composite probes whose interface name identifies CMSIS-DAP.
        for interface in node.get('IORegistryEntryChildren', []):
            if 'idVendor' not in interface:
                names += [interface.get('USB Interface Name', ''),
                          interface.get('IORegistryEntryName', '')]
        if is_cmsis_dap(vendor, device, names):
            serial = node.get('USB Serial Number') or node.get('kUSBSerialNumberString', '')
            probes.append(Probe(serial.strip(), product, vendor, device))
    return probes


def read_attribute(path):
    try:
        return path.read_text(errors='replace').strip()
    except OSError:
        # USB devices can disappear while being enumerated.
        return ''


def linux_probes(usb_root=Path('/sys/bus/usb/devices')):
    if not usb_root.is_dir():
        raise OSError(f'Linux USB sysfs directory is unavailable: {usb_root}')
    probes = []
    entries = list(usb_root.iterdir())
    for entry in entries:
        try:
            vendor = int(read_attribute(entry / 'idVendor'), 16)
            device = int(read_attribute(entry / 'idProduct'), 16)
        except ValueError:
            continue
        product = read_attribute(entry / 'product')
        names = [product]
        names += [read_attribute(interface / 'interface') for interface in entries
                  if interface.name.startswith(entry.name + ':')]
        if is_cmsis_dap(vendor, device, names):
            probes.append(Probe(read_attribute(entry / 'serial'), product, vendor, device))
    return probes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-only', action='store_true',
                        help='print just the serial; requires exactly one attached probe')
    args = parser.parse_args()
    try:
        if sys.platform == 'darwin':
            result = subprocess.run(['ioreg', '-p', 'IOUSB', '-l', '-a'],
                                    capture_output=True, check=True)
            probes = macos_probes(plistlib.loads(result.stdout))
        elif sys.platform.startswith('linux'):
            probes = linux_probes()
        else:
            parser.exit(1, 'Serial discovery supports macOS and Linux.\n')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = error.stderr.decode(errors='replace').strip() if (
            isinstance(error, subprocess.CalledProcessError) and error.stderr) else str(error)
        parser.exit(1, f'Could not enumerate USB devices: {detail}\n')
    if not probes:
        parser.exit(1, 'No CMSIS-DAP USB probes found. Connect the XIAO with a USB data cable and retry.\n')
    probes.sort(key=lambda probe: (probe.serial, probe.product, probe.vendor, probe.device))
    if args.serial_only:
        if len(probes) != 1:
            parser.exit(1, 'Multiple CMSIS-DAP probes found. Run without --serial-only and select a serial number.\n')
        if not probes[0].serial:
            parser.exit(1, 'The attached CMSIS-DAP probe does not report a USB serial number.\n')
        print(probes[0].serial)
        return
    print('SERIAL\tUSB ID\tDEVICE')
    for probe in probes:
        print(f'{probe.serial or "(not provided)"}\t{probe.vendor:04x}:{probe.device:04x}\t{probe.product or "CMSIS-DAP"}')


if __name__ == '__main__':
    main()
