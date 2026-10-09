#!/usr/bin/env python3
"""Validate the editable KiCad project, then export review/fabrication files.

Usage (from any directory):
    python3 /path/to/hw/board/scripts/export.py

Requires KiCad 10 or later. KICAD_CLI may name the executable or its full path;
otherwise PATH and the standard macOS application location are searched.
No source generator is run. DRC refills zones and saves the editable PCB.
Manufacturing output is refreshed in both fabrication/ and mfr/.
"""

from pathlib import Path
import csv
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


BOARD_DIR = Path(__file__).resolve().parents[1]
NAME = "xiao-bma400"


def find_cli():
    override = os.environ.get("KICAD_CLI")
    if override:
        executable = shutil.which(os.path.expanduser(override))
        if not executable:
            raise RuntimeError(f"KICAD_CLI is not an executable: {override}")
        return executable
    executable = shutil.which("kicad-cli")
    if executable:
        return executable
    macos_cli = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if macos_cli.is_file() and os.access(macos_cli, os.X_OK):
        return str(macos_cli)
    raise RuntimeError("Cannot find kicad-cli; set KICAD_CLI to an existing KiCad executable.")


def run(cli, *arguments):
    command = [cli, *(str(argument) for argument in arguments)]
    print(f"+ {shlex.join(command)}", flush=True)
    subprocess.run(command, cwd=BOARD_DIR, check=True)


def remove_testpads(source, destination):
    """A test pad is copper, not a component for the placement machine."""
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        if not fields:
            raise RuntimeError("KiCad produced an empty placement CSV.")
        reference_field = next((field for field in fields if field.lower() in ("ref", "reference")), None)
        if reference_field is None:
            raise RuntimeError(f"Unrecognized placement CSV header: {fields}")
        rows = [row for row in reader if not re.fullmatch(r"TP\d+", row[reference_field])]
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def publish_manufacturing(staging, destination):
    """Replace generated artifacts and remove obsolete output formats only."""
    destination.mkdir(exist_ok=True)
    artifacts = {artifact.name for artifact in staging.iterdir()}
    for artifact in sorted(staging.iterdir()):
        shutil.copy2(artifact, destination / artifact.name)

    # Earlier exports used Protel extensions. Keep one current set of layers;
    # otherwise fabricators can accidentally load duplicate or obsolete copper.
    layers = {
        "F_Cu": "gtl", "B_Cu": "gbl", "F_Paste": "gtp", "B_Paste": "gbp",
        "F_Silkscreen": "gto", "B_Silkscreen": "gbo",
        "F_Mask": "gts", "B_Mask": "gbs", "Edge_Cuts": "gm1",
    }
    managed = {
        f"{NAME}-{layer}.{extension}"
        for layer, protel_extension in layers.items()
        for extension in ("gbr", protel_extension)
    }
    for filename in managed - artifacts:
        obsolete = destination / filename
        if obsolete.is_file():
            obsolete.unlink()


def main():
    cli = find_cli()
    schematic = BOARD_DIR / f"{NAME}.kicad_sch"
    pcb = BOARD_DIR / f"{NAME}.kicad_pcb"
    project = BOARD_DIR / f"{NAME}.kicad_pro"
    for source in (schematic, pcb, project):
        if not source.is_file():
            raise RuntimeError(f"Missing editable project source: {source}")
    reports = BOARD_DIR / "reports"
    manufacturing_directories = (BOARD_DIR / "fabrication", BOARD_DIR / "mfr")
    reports.mkdir(exist_ok=True)

    # These checks must succeed before any fabrication export is attempted.
    # Both error and warning severities are checked by KiCad's default policy.
    run(cli, "sch", "erc", "--exit-code-violations", "--output", reports / "erc.rpt", schematic)
    run(cli, "sch", "export", "netlist", "--format", "kicadxml",
        "--output", reports / f"{NAME}.xml", schematic)
    run(cli, "pcb", "drc", "--refill-zones", "--save-board", "--schematic-parity",
        "--exit-code-violations", "--output", reports / "drc.rpt", pcb)

    run(cli, "sch", "export", "pdf", "--no-background-color",
        "--output", reports / "schematic.pdf", schematic)
    for side, layers, mirrored in (
        ("top", "F.Cu,F.SilkS,Edge.Cuts", False),
        ("bottom", "B.Cu,B.SilkS,Edge.Cuts", True),
    ):
        arguments = ["pcb", "export", "svg", "--mode-single", "--layers", layers,
                     "--page-size-mode", "2", "--exclude-drawing-sheet", "--drill-shape-opt", "2",
                     "--output", reports / f"pcb-{side}.svg"]
        if mirrored:
            arguments.append("--mirror")
        run(cli, *arguments, pcb)
    run(cli, "pcb", "export", "step", "--force",
        "--output", reports / "xiao-mg24-bma400-assembly.step", pcb)

    # Stage the complete manufacturing output before replacing existing files.
    # Gerber, drill and placement exports all use the same absolute PCB origin.
    with tempfile.TemporaryDirectory(prefix=f"{NAME}-export-") as temporary:
        staging = Path(temporary)
        gerber_directory = staging / "fabrication"
        gerber_directory.mkdir()
        run(cli, "pcb", "export", "gerbers",
            "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
            "--no-protel-ext",
            "--subtract-soldermask", "--output", str(gerber_directory) + os.sep, pcb)
        run(cli, "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "absolute",
            "--excellon-units", "mm", "--excellon-separate-th", "--generate-map", "--map-format", "pdf",
            "--generate-report", "--report-path", gerber_directory / f"{NAME}-drill-report.txt",
            "--output", str(gerber_directory) + os.sep, pcb)
        raw_positions = staging / "front-smd-unfiltered.csv"
        run(cli, "pcb", "export", "pos", "--side", "front", "--format", "csv", "--units", "mm",
            "--smd-only", "--exclude-fp-th", "--exclude-dnp", "--output", raw_positions, pcb)
        remove_testpads(raw_positions, gerber_directory / f"{NAME}-front-smd.csv")
        bom = BOARD_DIR / "bom.csv"
        if bom.is_file():
            shutil.copy2(bom, gerber_directory / "bom.csv")
        for destination in manufacturing_directories:
            publish_manufacturing(gerber_directory, destination)

    destinations = ", ".join(str(path) for path in manufacturing_directories)
    print(f"Validation passed. Review files: {reports}\nManufacturing files: {destinations}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        print(f"KiCad failed with exit status {error.returncode}; export stopped.", file=sys.stderr)
        sys.exit(error.returncode if error.returncode > 0 else 1)
    except (OSError, RuntimeError, csv.Error) as error:
        print(f"Export stopped: {error}", file=sys.stderr)
        sys.exit(1)
