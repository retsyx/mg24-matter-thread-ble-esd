#!/usr/bin/env python3
"""Regenerate the purchasing BOM from parts.json; no CAD files are changed."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    catalog = json.loads((ROOT / 'parts.json').read_text())
    columns = [
        ('References', 'references'), ('Quantity', 'quantity'),
        ('Value or description', 'value'), ('Footprint', 'footprint'),
        ('Manufacturer', 'manufacturer'), ('Manufacturer part number', 'mpn'),
        ('Tolerance', 'tolerance'), ('Voltage rating', 'voltage'),
        ('Dielectric', 'dielectric'), ('Power rating', 'power'),
        ('Datasheet (local PDF)', 'datasheet_file'), ('Datasheet URL', 'datasheet_url'),
        ('Supplier', 'supplier'), ('Supplier part number', 'supplier_part_number'),
        ('Purchase URL', 'purchase_url'), ('Stock shown (snapshot only)', 'stock_on_check'),
        ('Availability checked on', 'checked_on'), ('Assembly', 'assembly'),
        ('On board', 'on_board'), ('Purchased', 'purchased'), ('Notes', 'notes'),
    ]
    rows = []
    for entry in catalog['parts']:
        part = dict(entry)
        part['references'] = ','.join(part['references'])
        part['checked_on'] = (part.get('availability_checked_on', catalog['availability_checked_on'])
                              if part['purchased'] else '')
        part.update({key: part['properties'].get(field, '') for key, field in
                     [('tolerance', 'Tolerance'), ('voltage', 'Voltage'),
                      ('dielectric', 'Dielectric'), ('power', 'Power')]})
        rows.append([part.get(key, '') for _, key in columns])
    for target in [ROOT / 'bom.csv', ROOT / 'mfr' / 'bom.csv']:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('w', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow([name for name, _ in columns])
            writer.writerows(rows)
        print(f'Wrote {len(rows)} BOM groups to {target}')


if __name__ == '__main__':
    main()
