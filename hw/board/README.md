# XIAO MG24 and BMA400 PCB


## BOM

| References | Manufacturer / part | Datasheet |
| --- | --- | --- |
| U1 | Seeed Studio **102010590** | [Module schematic](datasheets/seeed-xiao-mg24-schematic.pdf) |
| U2 | Bosch Sensortec **BMA400** | [BMA400](datasheets/bosch-bma400.pdf) |
| J1 | JST **S2B-PH-K-S(LF)(SN)** | [PH series](datasheets/jst-ph.pdf) |
| R1, R2 | Panasonic **ERJ-3EKF1002V** | [ERJ series](datasheets/panasonic-erj-thick-film.pdf) |
| C1, C2 | KEMET **C0603C104K5RACTU** | [X7R series](datasheets/kemet-x7r-smd.pdf) |
| C3 | KEMET **C0603C105K4RACTU** | | [X7R series](datasheets/kemet-x7r-smd.pdf) |

Order the [standard XIAO MG24](https://www.seeedstudio.com/Seeed-Studio-XIAO-MG24-p-6247.html), without fitted pin headers.

## PCB Files and Editing

The PCB is two-layer, 1.6 mm FR4.

After editing, run the installed KiCad validation/export helper from the repository root:

```sh
python3 hw/board/scripts/export.py
python3 hw/board/scripts/render.py
```

Source generators overwrite their targets:

* `generate_schematic.py` rebuilds the schematic and local symbol library
* `generate_bom.py` rebuilds both BOM copies.
* `generate_board.py` requires KiCad's existing `pcbnew` Python module and the XML netlist. Preserve manual layout changes before generating a PCB.
*  Property-only updates can use `sync_board_properties.py` to preserve the layout.
