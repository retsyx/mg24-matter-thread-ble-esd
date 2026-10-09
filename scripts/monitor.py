#!/usr/bin/env python3
"""115200-baud USB serial monitor; uses the Python standard library only."""
import argparse
from collections import deque
import os
import select
import sys
import termios
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True)
parser.add_argument('--duration', type=float, default=0, help='seconds; zero runs until interrupted')
parser.add_argument('--command', action='append', default=[], help='send a shell command after opening')
args = parser.parse_args()
if args.duration < 0:
    parser.error('--duration must be nonnegative')
fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
saved = termios.tcgetattr(fd)
cfg = termios.tcgetattr(fd)
cfg[0] = cfg[1] = cfg[3] = 0
cfg[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
cfg[4] = cfg[5] = termios.B115200
cfg[6][termios.VMIN] = cfg[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, cfg)
start = time.monotonic()
commands = deque(args.command)
outgoing = b''
next_command = start
stdin_open = sys.stdin.isatty()
try:
    while not args.duration or time.monotonic() - start < args.duration:
        now = time.monotonic()
        if commands and not outgoing and now >= next_command:
            outgoing = (commands.popleft() + '\r\n').encode()
        readers = [fd, sys.stdin] if stdin_open else [fd]
        timeout = 0.2
        if commands and not outgoing:
            timeout = min(timeout, max(0, next_command - now))
        ready, writable, _ = select.select(readers, [fd] if outgoing else [], [], timeout)
        if fd in ready:
            data = os.read(fd, 8192)
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
        if fd in writable:
            try:
                outgoing = outgoing[os.write(fd, outgoing):]
            except BlockingIOError:
                pass
            if not outgoing:
                # The SDK shell can lose commands sent back to back. Continue
                # receiving its output while waiting to send the next command.
                next_command = time.monotonic() + 0.3
        if sys.stdin in ready:
            line = sys.stdin.readline()
            if line:
                commands.append(line.rstrip('\r\n'))
            else:
                stdin_open = False
except KeyboardInterrupt:
    pass
finally:
    termios.tcsetattr(fd, termios.TCSANOW, saved)
    os.close(fd)
