#!/usr/bin/env python3
"""Generate the portable, single-sheet XIAO MG24/BMA400 schematic.

Run from any directory. Only schematic and symbol-library files are replaced.
All coordinates are millimetres. UUIDs are stable across regeneration.
Purchasing fields and electrical ratings come from the board's parts.json.
"""

from pathlib import Path
import json
import uuid

OUT = Path(__file__).resolve().parents[1]
NAME = "xiao-bma400"
ROOT_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{NAME}/sheet"))


def load_parts():
    """Index the purchasing catalog and reject incomplete physical parts."""
    catalog = json.loads((OUT / "parts.json").read_text())
    by_reference = {}
    required = ("manufacturer", "mpn", "datasheet_url", "datasheet_file",
                "supplier", "supplier_part_number", "purchase_url")
    for part in catalog["parts"]:
        references = part["references"]
        if not isinstance(references, list) or not references:
            raise ValueError("Each parts.json entry must have a nonempty references list")
        if part.get("on_board") and part.get("purchased"):
            missing = [field for field in required
                       if not isinstance(part.get(field), str) or not part[field].strip()]
            if missing:
                raise ValueError(f"Incomplete purchasing metadata for {references}: {', '.join(missing)}")
            datasheet_file = Path(part["datasheet_file"])
            if datasheet_file.is_absolute() or ".." in datasheet_file.parts:
                raise ValueError(f"Datasheet file must be project-relative for {references}")
        if not isinstance(part.get("properties", {}), dict):
            raise ValueError(f"Part properties must be an object for {references}")
        if set(part.get("properties", {})) & {"Reference", "Value", "Footprint", "Datasheet"}:
            raise ValueError(f"Part properties cannot override schematic identity fields for {references}")
        for reference in references:
            if reference in by_reference:
                raise ValueError(f"Duplicate parts.json reference: {reference}")
            by_reference[reference] = part
    return by_reference


PARTS_BY_REFERENCE = load_parts()


def uid(key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{NAME}/{key}"))


def q(value):
    return json.dumps(str(value))


def n(value):
    return f"{value:.4f}".rstrip("0").rstrip(".") if value else "0"


def effects(size=1.27, hide=False, justify="", bold=False):
    return (f"(effects (font (size {n(size)} {n(size)}){' (bold yes)' if bold else ''})"
            f"{' (justify ' + justify + ')' if justify else ''}"
            f"{' (hide yes)' if hide else ''})")


def prop(name, value, x, y, hide=False, size=1.27, justify=""):
    return f"(property {q(name)} {q(value)} (at {n(x)} {n(y)} 0) {effects(size, hide, justify)})"


def pin(number, name, kind, x, y, angle, length=5.08):
    return (f"(pin {kind} line (at {n(x)} {n(y)} {angle}) (length {n(length)})"
            f" (name {q(name)} {effects(1.016)}) (number {q(number)} {effects(1.016)}))")


def rect(x1, y1, x2, y2):
    return (f"(rectangle (start {n(x1)} {n(y1)}) (end {n(x2)} {n(y2)})"
            " (stroke (width 0.254) (type default)) (fill (type background)))")


def line(points, width=.254):
    pts = " ".join(f"(xy {n(x)} {n(y)})" for x, y in points)
    return f"(polyline (pts {pts}) (stroke (width {n(width)}) (type default)) (fill (type none)))"


symbols = {}
pins = {}


def symbol(name, ref, footprint, pin_defs, graphics, datasheet="", desc="", power=False):
    pins[name] = {str(p[0]): p for p in pin_defs}
    hidden_pins = name in ("R", "C", "TestPoint", "PWR_FLAG")
    symbols[name] = (f"(symbol {q(name)} {'(power)' if power else ''}"
                     + (' (pin_numbers (hide yes))' if hidden_pins else '')
                     + f" (pin_names (offset 1.016){' (hide yes)' if hidden_pins else ''}) (exclude_from_sim no)"
                     f" (in_bom {'no' if power else 'yes'}) (on_board {'no' if power else 'yes'})"
                     + prop("Reference", ref, 0, 5.08)
                     + prop("Value", name, 0, -5.08)
                     + prop("Footprint", footprint, 0, 0, True)
                     + prop("Datasheet", datasheet, 0, 0, True)
                     + prop("Description", desc, 0, 0, True)
                     + f"(symbol {q(name + '_0_1')} {graphics})"
                     + f"(symbol {q(name + '_1_1')} "
                     + " ".join(pin(*p) for p in pin_defs) + "))")


u1pins = []
leftnames = ["D0 / PC0", "D1 / PC1", "D2 / PC2", "D3 / PC3",
             "D4 / PC4 / SDA", "D5 / PC5 / SCL", "D6 / PC6 / TX"]
for i, name in enumerate(leftnames):
    u1pins.append((str(i + 1), name, "bidirectional", -22.86, 15.24 - i * 5.08, 0))
for number, name, typ, y in [(14, "5V / VBUS", "passive", 15.24),
                              (13, "GND", "power_in", 10.16),
                              (12, "3V3", "power_out", 5.08),
                              (11, "D10 / PA5 / MOSI", "bidirectional", 0),
                              (10, "D9 / PA4 / MISO", "bidirectional", -5.08),
                              (9, "D8 / PA3 / SCK", "bidirectional", -10.16),
                              (8, "D7 / PC7 / RX", "bidirectional", -15.24),
                              (31, "BAT+", "passive", -20.32),
                              (32, "BAT-", "power_in", -25.4)]:
    u1pins.append((str(number), name, typ, 22.86, y, 180))
symbol("XIAO_MG24", "U", "Board:XIAO_MG24_SMD", u1pins,
       rect(-17.78, 19.05, 17.78, -29.21),
       PARTS_BY_REFERENCE["U1"]["datasheet_url"],
       "Seeed Studio XIAO MG24; carrier contacts 1..14, 31=BAT+, 32=BAT-. Underside contacts 15..30 omitted. Onboard PD3/PD4 switched battery divider.")

symbol("BMA400", "U", "Board:LGA-12_2x2mm_P0.5mm", [
    ("1", "SDO", "input", -15.24, -2.54, 0),
    ("2", "SDX / SDA", "bidirectional", -15.24, 10.16, 0),
    ("3", "VDDIO", "power_in", -5.08, 25.4, 270),
    ("4", "NC", "no_connect", 15.24, -5.08, 180),
    ("5", "INT1", "output", 15.24, 10.16, 180),
    ("6", "INT2", "output", 15.24, 5.08, 180),
    ("7", "VDD", "power_in", 5.08, 25.4, 270),
    ("8", "GNDIO", "power_in", -5.08, -25.4, 90),
    ("9", "GND", "power_in", 5.08, -25.4, 90),
    ("10", "CSB", "input", -15.24, -7.62, 0),
    ("11", "NC", "no_connect", 15.24, -10.16, 180),
    ("12", "SCX / SCL", "input", -15.24, 5.08, 0),
], rect(-10.16, 20.32, 10.16, -20.32),
       "https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bma400-ds000.pdf",
       "Bosch BMA400, LGA-12 2x2 mm, I2C address 0x14 with SDO low and CSB high")

symbol("R", "R", "Board:R_0603_1608Metric", [
    ("1", "~", "passive", 0, 3.81, 270, 2.54),
    ("2", "~", "passive", 0, -3.81, 90, 2.54),
], rect(-1.016, 1.27, 1.016, -1.27), desc="Resistor, 0603 imperial / 1608 metric")

symbol("C", "C", "Board:C_0603_1608Metric", [
    ("1", "~", "passive", 0, 3.81, 270, 3.175),
    ("2", "~", "passive", 0, -3.81, 90, 3.175),
], line([(-1.905, .635), (1.905, .635)]) + line([(-1.905, -.635), (1.905, -.635)]),
       desc="Ceramic capacitor, 0603 imperial / 1608 metric")

symbol("Battery_2", "J", "", [
    ("1", "-", "passive", 5.08, 1.27, 180, 2.54),
    ("2", "+", "passive", 5.08, -3.81, 180, 2.54),
], rect(-2.54, 3.81, 2.54, -6.35), desc="Battery connector, pin 1 negative and pin 2 positive")

symbol("PWR_FLAG", "#FLG", "", [
    ("1", "pwr", "power_out", 0, 0, 90, 0),
], line([(0, 0), (0, 1.27), (-1.27, 1.905), (0, 2.54), (1.27, 1.905), (0, 1.27)]),
       desc="Declare external battery/ground power source for ERC", power=True)

items = []
placed = {}


def place(lib, ref, value, x, y, footprint=None, datasheet="", extras=None):
    power = ref.startswith("#")
    extras = dict(extras or {})
    if not power:
        part = PARTS_BY_REFERENCE.get(ref)
        if not part or not part.get("on_board") or not part.get("purchased"):
            raise ValueError(f"Missing purchased on-board part in parts.json: {ref}")
        datasheet = part["datasheet_url"]
        extras.update({
            "Manufacturer": part["manufacturer"],
            "MPN": part["mpn"],
            "Datasheet file": "${KIPRJMOD}/" + part["datasheet_file"],
            "Supplier": part["supplier"],
            "Supplier part number": part["supplier_part_number"],
            "Purchase URL": part["purchase_url"],
        })
        extras.update(part.get("properties", {}))
    placed[ref] = (lib, x, y)
    fp = footprint if footprint is not None else {
        "XIAO_MG24": "Board:XIAO_MG24_SMD", "BMA400": "Board:LGA-12_2x2mm_P0.5mm",
        "R": "Board:R_0603_1608Metric", "C": "Board:C_0603_1608Metric",
        "PWR_FLAG": "",
    }[lib]
    if lib in ("XIAO_MG24", "BMA400"):
        refpos, valpos = (x, y-25.4), (x, y-22.86)
        if lib == "BMA400":
            refpos, valpos = (x-20.32, y-24.13), (x-20.32, y-21.59)
    elif lib in ("R", "C"):
        refpos, valpos = (x+2.54, y-1.27), (x+2.54, y+1.27)
    elif lib == "Battery_2":
        refpos, valpos = (x, y-8.89), (x, y-6.35)
    else:
        refpos, valpos = (x, y-6.35), (x, y-8.89)
        if power:
            valpos = (x, y-5.08)
    justify = "left" if lib in ("R", "C") else ""
    item = (f"(symbol (lib_id {q('Board:' + lib)}) (at {n(x)} {n(y)} 0) (unit 1)"
            f" (exclude_from_sim no) (in_bom {'no' if power else 'yes'})"
            f" (on_board {'no' if power else 'yes'}) (dnp no) (uuid {q(uid(ref))})"
            + prop("Reference", ref, *refpos, hide=power, justify=justify)
            + prop("Value", value, *valpos, hide=lib == "TestPoint", justify=justify)
            + prop("Footprint", fp, x, y, True)
            + prop("Datasheet", datasheet, x, y, True)
            + "".join(prop(k, v, x, y, True) for k, v in extras.items())
            + "".join(f"(pin {q(p)} (uuid {q(uid(ref + '/pin/' + p))}))" for p in pins[lib])
            + f"(instances (project {q(NAME)} (path {q('/' + ROOT_UUID)} (reference {q(ref)}) (unit 1)))))")
    items.append(item)


def pxy(ref, number):
    lib, x, y = placed[ref]
    p = pins[lib][str(number)]
    return round(x + p[3], 4), round(y - p[4], 4)


def wire(a, b):
    if a == b:
        return
    items.append(f"(wire (pts (xy {n(a[0])} {n(a[1])}) (xy {n(b[0])} {n(b[1])}))"
                 f" (stroke (width 0) (type default)) (uuid {q(uid('wire/' + str((a, b))))}))")


def label(name, x, y, angle=0):
    items.append(f"(label {q(name)} (at {n(x)} {n(y)} {angle}) {effects(1.016, justify='left bottom')}"
                 f" (uuid {q(uid('label/' + str((name, x, y))))}))")


def net(ref, number, name, length=7.62):
    x, y = pxy(ref, number)
    lib = placed[ref][0]
    angle = pins[lib][str(number)][5]
    dx, dy = {0: (-length, 0), 180: (length, 0), 90: (0, length), 270: (0, -length)}[angle]
    end = (round(x+dx, 4), round(y+dy, 4))
    wire((x, y), end)
    label(name, *end, 0)


def nc(ref, number):
    x, y = pxy(ref, number)
    items.append(f"(no_connect (at {n(x)} {n(y)}) (uuid {q(uid('NC/' + ref + '/' + str(number)))}))")


def note(value, x, y, size=1.27, bold=False):
    items.append(f"(text {q(value)} (at {n(x)} {n(y)} 0) {effects(size, justify='left', bold=bold)}"
                 f" (uuid {q(uid('note/' + value))}))")


# Top half: XIAO module and sensor. Labels tie repeated net names together.
note("Thread / BLE motion sensor", 17.78, 15.24, 2.54, True)
note("XIAO MG24 + Bosch BMA400  |  single-cell Li-ion / LiPo", 17.78, 21.59, 1.27)
place("XIAO_MG24", "U1", "XIAO MG24", 60.96, 62.23)
for number, name in {3:"ACC_INT1", 5:"I2C_SDA", 6:"I2C_SCL", 12:"+3V3", 13:"GND", 31:"VBAT", 32:"GND"}.items():
    net("U1", number, name)
for number in (1, 2, 4, 7, 8, 9, 10, 11, 14):
    nc("U1", number)
note("USB-C, charger and 3.3 V regulator are on U1.", 22.86, 100.33, 1.016)
note("Surface-mount U1; underside pad 31 is BAT+, pad 32 is BAT-.", 22.86, 105.41, 1.016)

place("BMA400", "U2", "BMA400", 182.88, 62.23,
      extras={"I2C address":"0x14"})
for number, name in {1:"GND",2:"I2C_SDA",3:"+3V3",5:"ACC_INT1",7:"+3V3",8:"GND",9:"GND",10:"+3V3",12:"I2C_SCL"}.items():
    net("U2", number, name)
for number in (4, 6, 11):
    nc("U2", number)
note("I2C mode: CSB high, SDO low -> address 0x14.", 154.94, 100.33, 1.016)

# Pull-ups in the upper right.
note("I2C pull-ups", 238.76, 30.48, 1.524, True)
for ref, x, signal in [("R1", 238.76, "I2C_SDA"), ("R2", 264.16, "I2C_SCL")]:
    place("R", ref, "10k", x, 49.53)
    net(ref, 1, "+3V3")
    net(ref, 2, signal)

note("Supply decoupling", 228.6, 72.39, 1.524, True)
for ref, val, x in [("C1", "100nF", 228.6), ("C2", "100nF", 246.38), ("C3", "1uF", 264.16)]:
    place("C", ref, val, x, 87.63)
    net(ref, 1, "+3V3", 5.08)
    net(ref, 2, "GND", 5.08)
note("C1 at VDDIO; C2 at VDD; C3 bulk.", 228.6, 104.14, 1.016)

# Battery entry: routed directly to the module's underside battery contacts.
note("Battery and charger connection", 17.78, 111.76, 1.524, True)
place("Battery_2", "J1", "BATTERY / JST-PH 2.0", 38.1, 132.08,
      footprint=PARTS_BY_REFERENCE["J1"]["footprint"])
net("J1", 1, "GND", 12.7)
net("J1", 2, "VBAT", 12.7)
place("PWR_FLAG", "#FLG01", "PWR_FLAG", 73.66, 132.08)
wire((73.66,132.08),(73.66,137.16))
label("GND",73.66,137.16)
place("PWR_FLAG", "#FLG02", "PWR_FLAG", 91.44, 132.08)
wire((91.44,132.08),(91.44,137.16))
label("VBAT",91.44,137.16)
note("J1 pin 1 -> GND/BAT-; pin 2 -> VBAT/BAT+.", 17.78, 153.67, 1.016, True)
note("U1 provides USB charging at 200 mA; its charge LED is not a fuel gauge.", 17.78, 161.29, 1.016)
note("Use a protected 1-cell 3.7 V nominal pack (4.2 V full); verify lead polarity.", 17.78, 168.91, 1.016)
note("U1 has switched VBAT / 2 sensing: PD3 enable, PD4 ADC.", 17.78, 176.53, 1.016)
note("No external divider; D1 is unused. Other underside contacts are omitted.", 17.78, 184.15, 1.016)

library = '(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor")\n'
library += "\n".join(symbols.values()) + "\n)\n"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "board.kicad_sym").write_text(library)
(OUT / "sym-lib-table").write_text('(sym_lib_table\n  (version 7)\n  (lib (name "Board")(type "KiCad")(uri "${KIPRJMOD}/board.kicad_sym")(options "")(descr "Project-local portable board symbols"))\n)\n')
embedded = "\n".join(s.replace(f'(symbol {q(name)}', f'(symbol {q("Board:" + name)}', 1)
                       for name, s in symbols.items())
sheet = (f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0")'
         f' (uuid {q(ROOT_UUID)}) (paper "A4")'
         ' (title_block (title "XIAO MG24 / BMA400 Motion Sensor") (date "2026-10-06")'
         ' (rev "E") (company "mg24-matter-thread-ble-esd")'
         ' (comment 1 "2-layer SMD carrier; protected 1S battery; underside BAT contacts"))'
         f'\n(lib_symbols {embedded})\n' + "\n".join(items)
         + '\n(sheet_instances (path "/" (page "1"))) (embedded_fonts no)\n)\n')
(OUT / f"{NAME}.kicad_sch").write_text(sheet)
print(f"Generated {OUT / (NAME + '.kicad_sch')} ({len(placed)} symbols)")
