#!/usr/bin/env python3
"""Copy schematic component properties to the existing PCB without rerouting it.

Export reports/xiao-bma400.xml from the schematic first. Run this script with
KiCad's Python interpreter (the pcbnew module is required), then export.py.
This updates fields only: pads, nets, placement, tracks and zones stay intact.
"""

from pathlib import Path
import xml.etree.ElementTree as ET
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
NAME = 'xiao-bma400'


def geometry(board):
    """Guard the physical layout against accidental changes during field sync."""
    def pos(point):
        return point.x, point.y

    return (
        sorted((fp.GetReference(), pos(fp.GetPosition()), fp.GetOrientationDegrees(),
                tuple(sorted((pad.GetNumber(), pos(pad.GetPosition()),
                              pos(pad.GetSize()), pad.GetNetname()) for pad in fp.Pads())))
               for fp in board.GetFootprints()),
        sorted((track.GetClass(), pos(track.GetStart()), pos(track.GetEnd()),
                track.GetWidth(track.GetLayer()) if isinstance(track, p.PCB_VIA) else track.GetWidth(),
                track.GetLayer(), track.GetNetname())
               for track in board.GetTracks()),
        len(list(board.Zones())),
    )


def main():
    path = ROOT / (NAME + '.kicad_pcb')
    board = p.LoadBoard(str(path))
    before = geometry(board)
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    root = ET.parse(ROOT / 'reports' / (NAME + '.xml')).getroot()
    updated = 0
    for component in root.find('components'):
        ref = component.attrib['ref']
        fp = footprints[ref]
        # A changed footprint or value requires deliberate electrical review.
        assert fp.GetValue() == component.findtext('value'), ref + ': value changed'
        assert fp.GetFPID().GetLibItemName() == component.findtext('footprint').split(':', 1)[1], ref + ': footprint changed'
        fp.GetField(p.FIELD_T_DATASHEET).SetText(component.findtext('datasheet') or '')
        for item in component.findall('fields/field'):
            name = item.attrib['name']
            if name in ('Footprint', 'Datasheet', 'Description'):
                continue
            field = fp.GetField(name)
            if field is None:
                field = p.PCB_FIELD(fp, p.FIELD_T_USER, name)
                field.SetVisible(False)
                fp.Add(field)
            field.SetText(item.text or '')
        updated += 1
    assert geometry(board) == before, 'Unexpected layout change'
    p.SaveBoard(str(path), board)
    assert geometry(p.LoadBoard(str(path))) == before, 'Unexpected saved layout change'
    print(f'Updated properties for {updated} footprints; physical layout preserved.')


if __name__ == '__main__':
    main()
