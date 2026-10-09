#!/usr/bin/env python3
"""Render the editable PCB using its project-local 3D models (KiCad 10+)."""

import subprocess
import sys

from export import BOARD_DIR, NAME, find_cli, run


def main():
    cli = find_cli()
    reports = BOARD_DIR / "reports"
    reports.mkdir(exist_ok=True)
    run(cli, "pcb", "render", "--quality", "high",
        "--width", "1600", "--height", "1200",
        "--background", "opaque", "--side", "top", "--rotate", "325,0,30",
        "--zoom", "0.8",
        "--output", reports / "pcb-3d.png", BOARD_DIR / f"{NAME}.kicad_pcb")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Render failed: {error}", file=sys.stderr)
        sys.exit(1)
