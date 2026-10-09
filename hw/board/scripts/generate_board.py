#!/usr/bin/env python3
"""Rebuild the carrier PCB with KiCad's bundled Python/pcbnew.

The checked-in PCB is the editable design; regeneration overwrites PCB edits.
Run generate_schematic.py and export its XML netlist before this script.
"""
from pathlib import Path
import json
import os
import xml.etree.ElementTree as ET
import pcbnew as p

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'Board.pretty'
STOCK = Path(os.environ.get('KICAD_FOOTPRINT_DIR', '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints'))
NAME = 'xiao-bma400'

def mm(v): return p.FromMM(v)
def xy(x, y): return p.VECTOR2I(mm(x), mm(y))

def custom(name, body):
    (LIB / (name + '.kicad_mod')).write_text('(footprint "'+name+'" (version 20240108) (generator "pcbnew") (layer "F.Cu")\n'+body+'\n)\n')

def line(a,b,layer='F.SilkS',width=.12):
    return f'(fp_line (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (stroke (width {width}) (type solid)) (layer "{layer}"))\n'

def rect(x1,y1,x2,y2,layer='F.CrtYd',width=.05):
    return ''.join(line(a,b,layer,width) for a,b in zip([(x1,y1),(x2,y1),(x2,y2),(x1,y2)],[(x2,y1),(x2,y2),(x1,y2),(x1,y1)]))

def props(value, refy=-2):
    return f'(property "Reference" "REF**" (at 0 {refy} 0) (layer "F.SilkS") (effects (font (size .8 .8) (thickness .12))))\n(property "Value" "{value}" (at 0 0 0) (layer "F.Fab") (effects (font (size .8 .8) (thickness .12))))\n'

LIB.mkdir(exist_ok=True)
# The verified MG24 footprint is maintained in Board.pretty. It includes the
# module's actual underside battery contacts and its Seeed STEP assembly model.
if not (LIB / 'XIAO_MG24_SMD.kicad_mod').is_file():
    raise RuntimeError('Missing project-local XIAO MG24 footprint')
stock_parts={
    'R_0603_1608Metric':'Resistor_SMD', 'C_0603_1608Metric':'Capacitor_SMD',
    'LGA-12_2x2mm_P0.5mm':'Package_LGA',
    'JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal':'Connector_JST',
    'TestPoint_Pad_D1.0mm':'TestPoint',
    'MountingHole_2.2mm_M2':'MountingHole',
}
for name,lib in stock_parts.items():
    target=LIB/(name+'.kicad_mod')
    if not target.exists():
        f=p.FootprintLoad(str(STOCK/(lib+'.pretty')),name)
        if not f: raise RuntimeError('Missing footprint '+name)
        f.Models().clear() # Replace stock paths with the included project-local STEP files.
        if name in ('R_0603_1608Metric', 'C_0603_1608Metric',
                    'JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal'):
            model=p.FP_3DMODEL()
            model.m_Filename='${KIPRJMOD}/3dmodels/'+name+'.step'
            f.Models().push_back(model)
        p.FootprintSave(str(LIB),f)
# Bosch datasheet section 7.5, recommended 0.30 x 0.35 mm copper lands.
s=props('BMA400',-2)+'(attr smd)\n'+rect(-1.25,-1.25,1.25,1.25)+rect(-1,-1,1,1,'F.Fab',.1)
s+=line((-1.45,-.6),(-1.45,-1.2))+line((-1.45,-1.2),(-.8,-1.2))
for n,x,y,w,h in [(1,-.775,-.75,.35,.3),(2,-.775,-.25,.35,.3),(3,-.775,.25,.35,.3),(4,-.775,.75,.35,.3),(5,-.25,.775,.3,.35),(6,.25,.775,.3,.35),(7,.775,.75,.35,.3),(8,.775,.25,.35,.3),(9,.775,-.25,.35,.3),(10,.775,-.75,.35,.3),(11,.25,-.775,.3,.35),(12,-.25,-.775,.3,.35)]:
    s+=f'(pad "{n}" smd rect (at {x} {y}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask") (solder_mask_margin .05) (solder_paste_margin -.025))\n'
# Generic LGA model, Z scaled from 1.025 to the BMA400's nominal 0.95 mm.
# This changes visualization only; the Bosch copper land pattern above is exact.
s+='''(model "${KIPRJMOD}/3dmodels/LGA-12_2x2mm_P0.5mm.step"
 (offset (xyz 0 0 0))
 (scale (xyz 1 1 0.926829268292683))
 (rotate (xyz 0 0 0))
)\n'''
custom('LGA-12_2x2mm_P0.5mm',s)
(ROOT/'fp-lib-table').write_text('(fp_lib_table\n (lib (name "Board")(type "KiCad")(uri "${KIPRJMOD}/Board.pretty")(options "")(descr "Project-local carrier footprints"))\n)\n')

# Netlist is the source of pin/net assignments and schematic UUIDs.
tree=ET.parse(ROOT/'reports'/f'{NAME}.xml').getroot()
components={c.attrib['ref']:c for c in tree.find('components')}
board=p.BOARD()
board.SetCopperLayerCount(2)
board.GetDesignSettings().SetBoardThickness(mm(1.6))
title=p.TITLE_BLOCK();title.SetTitle('XIAO MG24 / BMA400 Motion Sensor');title.SetRevision('E');title.SetDate('2026-10-06');board.SetTitleBlock(title)
netmap={}
pinmap={}
for net in tree.find('nets'):
    name=net.attrib['name']
    n=p.NETINFO_ITEM(board,name); board.Add(n); netmap[name.lstrip('/')]=n
    for node in net.findall('node'):
        pinmap[(node.attrib['ref'],node.attrib['pin'])]=n

placements={
 'U1':(64,59.5,90), 'U2':(57,78,0),
 'J1':(63,85,0),
 'R1':(54,74,270), 'R2':(51.5,74,270),
 'C1':(53.5,79.5,270), 'C2':(61,79.5,270),
 'C3':(65,80,270),
}
fps={}
for ref,(x,y,rot) in placements.items():
    c=components[ref]
    footprint=c.findtext('footprint')
    fp=p.FootprintLoad(str(LIB),footprint.split(':')[-1])
    fp.SetFPID(p.LIB_ID(*footprint.split(':', 1)))
    fp.SetReference(ref); fp.SetValue(c.findtext('value'))
    fp.GetField(p.FIELD_T_DATASHEET).SetText(c.findtext('datasheet') or '')
    for field in c.findall('fields/field'):
        if field.attrib['name'] not in ['Footprint','Datasheet','Description']:
            f=p.PCB_FIELD(fp,p.FIELD_T_USER,field.attrib['name']);f.SetText(field.text or '');f.SetVisible(False);fp.Add(f)
    fp.SetExcludedFromBOM(False)
    board.Add(fp); fp.SetPosition(xy(x,y)); fp.SetOrientationDegrees(rot)
    # Link footprint to its schematic symbol for parity checks and normal updates.
    sheet=c.find('sheetpath').attrib['tstamps']
    stamps=c.findtext('tstamps').split()[0]
    path=p.KIID_PATH()
    for item in (sheet.strip('/')+'/'+stamps.strip('/')).split('/'):
        if item: path.push_back(p.KIID(item))
    fp.SetPath(path)
    for pad in fp.Pads():
        key=(ref,pad.GetNumber())
        if key in pinmap: pad.SetNet(pinmap[key])
    fp.Reference().SetTextSize(xy(.75,.75)); fp.Reference().SetTextThickness(mm(.12))
    fp.Reference().SetTextAngle(p.EDA_ANGLE(0,p.DEGREES_T))
    fp.Value().SetVisible(False)
    fps[ref]=fp
fps['R2'].Reference().SetPosition(xy(50.1,74))

for ref,x,y in [('H1',52,89),('H2',76,89)]:
    f=p.FootprintLoad(str(LIB),'MountingHole_2.2mm_M2')
    board.Add(f); f.SetPosition(xy(x,y)); f.SetReference(ref)
    f.SetFPID(p.LIB_ID('Board','MountingHole_2.2mm_M2'))
    f.SetAttributes(p.FP_BOARD_ONLY|p.FP_EXCLUDE_FROM_BOM|p.FP_EXCLUDE_FROM_POS_FILES)
    f.Reference().SetVisible(False); f.Value().SetVisible(False)

def point(ref,pin):
    pos=next(a for a in fps[ref].Pads() if a.GetNumber()==str(pin)).GetPosition()
    return (p.ToMM(pos.x),p.ToMM(pos.y))

def track(net,points,layer='F.Cu',width=.25):
    for a,b in zip(points,points[1:]):
        if a==b: continue
        t=p.PCB_TRACK(board); t.SetStart(xy(*a));t.SetEnd(xy(*b));t.SetWidth(mm(width))
        t.SetLayer(p.F_Cu if layer=='F.Cu' else p.B_Cu);t.SetNet(netmap[net]);board.Add(t)

def via(net,x,y):
    v=p.PCB_VIA(board);v.SetPosition(xy(x,y));v.SetWidth(mm(.6));v.SetDrill(mm(.3))
    v.SetViaType(p.VIATYPE_THROUGH);v.SetLayerPair(p.F_Cu,p.B_Cu);v.SetNet(netmap[net]);board.Add(v)

def route(net,a,b,through=(),layer='F.Cu',width=.25):
    track(net,[point(*a),*through,point(*b)],layer,width)

# Sensor escapes use 0.15 mm traces; all other signals use 0.25 mm.
track('I2C_SDA',[point('U2',2),(55,77.65)],width=.15);via('I2C_SDA',55,77.65)
via('I2C_SDA',55,74.825)
track('I2C_SDA',[(55,77.65),(55.8,76.85),(55.8,75.8),(55,75),(55,74.825)],layer='B.Cu',width=.2)
track('I2C_SDA',[point('R1',2),(55,74.825)],width=.25)
route('I2C_SDA',('R1',2),('U1',5),[(53.25,74.825),(53.25,63.42),(55.08,62.04)])
route('I2C_SCL',('U2',12),('R2',2),[(56.75,76.5),(55.75,75.5),(51.5,75.5)],width=.15)
track('I2C_SCL',[point('R2',2),(52.5,74.825),(52.5,71)],width=.25)
via('I2C_SCL',52.5,71)
track('I2C_SCL',[(52.5,71),(54.25,69.45),(54.25,66.71),(56.9,64.58)],layer='B.Cu')
via('I2C_SCL',56.9,64.58)
track('I2C_SCL',[(56.9,64.58),point('U1',6)],width=.25)
# Retain the edited carrier's direct INT1 route; no test-pad spur.
track('ACC_INT1',[point('U2',5),(56.75,79.2),(56.523,79.427),
    (52.421354,79.427),(50.773,77.778646),(50.773,62.132),(53,59.905),(53,56.96),point('U1',3)],width=.25)

# Supply decoupling at both BMA400 supply pins.
route('+3V3',('U2',3),('C1',1),[(54.75,78.25)],width=.15)
route('+3V3',('U2',7),('C2',1),[(59.5,78.75)],width=.15)
route('+3V3',('U2',10),('C2',1),[(59.5,77.25),(60.2,77.95)],width=.15)
power_vias={'C1':(52.5,78.725),'C2':(62,78.725),'C3':(65,78.1),'R1':(54,72.2),'R2':(51.5,72.15)}
for ref,pos in power_vias.items():
    track('+3V3',[point(ref,1),pos],width=.25);via('+3V3',*pos)
track('+3V3',[power_vias['C1'],power_vias['C2'],power_vias['C3']],layer='B.Cu',width=.4)
track('+3V3',[point('U1',12),(74.4,56.96)],width=.4);via('+3V3',74.4,56.96)
track('+3V3',[(74.4,56.96),(73.5,57.86),(73.5,74.75),(73.475,74.75),(70.125,78.1),power_vias['C3']],layer='B.Cu',width=.4)
track('+3V3',[power_vias['R1'],(53,73.2),(51.95,72.15),power_vias['R2']],layer='B.Cu',width=.25)
track('+3V3',[power_vias['R1'],(53,73.2),(53,77.5),power_vias['C1']],layer='B.Cu',width=.25)

# Ground vias into the bottom plane, including both sensor grounds and address strap.
track('GND',[point('U2',1),(54.6,77),(54.6,76.6)],width=.15);via('GND',54.6,76.6)
track('GND',[(54.6,76.6),(51.5,76.6)],width=.25);via('GND',51.5,76.6)
track('GND',[point('U2',8),(58.3,78.25),(59,77.9),(58.3,77.75),point('U2',9)],width=.15);via('GND',59,77.9)
for ref in ['C1','C2','C3']:
    x,y=point(ref,2);track('GND',[(x,y),(x,y+.8)],width=.25);via('GND',x,y+.8)
track('GND',[point('U1',13),(74.4,54.42)],width=.4);via('GND',74.4,54.42)
track('GND',[point('U1',32),(66,65.0317)],width=.4);via('GND',66,65.0317)

# New MG24 underside battery contacts: pad 31 = VBAT, pad 32 = GND.
# Escape above the antenna area, then use the bottom layer to reach J1.
track('VBAT',[point('U1',31),(62.2186,62.8)],width=.6);via('VBAT',62.2186,62.8)
track('VBAT',[(62.2186,62.8),(68.3,62.8),(70.85,65.35),(71.9,66.4),
    (71.9,73)],layer='B.Cu',width=.6);via('VBAT',71.9,73)
track('VBAT',[(71.9,73),(71.9,76.2),(65,83.1),point('J1',2)],width=.6)

def graphic_line(a,b,layer,width=.1):
    s=p.PCB_SHAPE();s.SetShape(p.SHAPE_T_SEGMENT);s.SetStart(xy(*a));s.SetEnd(xy(*b));s.SetLayer(layer);s.SetWidth(mm(width));board.Add(s)
for a,b in [((49,50),(79,50)),((79,50),(79,92)),((79,92),(49,92)),((49,92),(49,50))]:
    graphic_line(a,b,p.Edge_Cuts,.05)

def text_at(txt,x,y,layer=p.F_SilkS,size=.85,angle=0):
    t=p.PCB_TEXT(board);t.SetText(txt);t.SetPosition(xy(x,y));t.SetTextSize(xy(size,size));t.SetTextThickness(mm(.13));t.SetLayer(layer);t.SetMirrored(layer==p.B_SilkS);t.SetTextAngle(p.EDA_ANGLE(angle,p.DEGREES_T));board.Add(t)
text_at('MG24 / BMA400',76,58,angle=270,size=1)
text_at('USB',64,51.2)
text_at('-',59.7,85);text_at('+',68.2,85)
text_at('1S LiPo',70.5,86.5,size=.65)
text_at('ANTENNA\nNO COPPER',64,68.8,p.Dwgs_User,1)
text_at('30 x 42 mm / 2 layers / 1.6 mm FR4',64,94,p.Dwgs_User,.8)

# Copper exclusions from the actual MG24 underside and antenna footprint.
# The stepped antenna boundary keeps the ceramic body clear on both layers,
# while leaving the adjacent castellated D7 pad's assembly land available.
def rule_area(name, vertices, layers):
    area=p.ZONE(board)
    area.SetIsRuleArea(True);area.SetZoneName(name)
    layer_set=p.LSET()
    for layer in layers: layer_set.AddLayer(layer)
    area.SetLayerSet(layer_set)
    area.SetDoNotAllowTracks(True);area.SetDoNotAllowVias(True)
    area.SetDoNotAllowPads(True);area.SetDoNotAllowZoneFills(True)
    outline=area.Outline();outline.NewOutline()
    for x,y in vertices: outline.Append(mm(x),mm(y))
    board.Add(area)

rule_area('MG24 antenna clearance',
    [(58,66.7),(70.5,66.7),(70.5,68.45),(71.4,68.45),(71.4,74),(58,74)],
    [p.F_Cu,p.B_Cu])
rule_area('Unused MG24 central SWD contacts',
    [(61.5,50),(66.5,50),(66.5,59.9),(61.5,59.9)],[p.F_Cu])
rule_area('Unused MG24 left GPIO contacts',
    [(57.9,54.6),(59.9,54.6),(59.9,64.4),(57.9,64.4)],[p.F_Cu])
rule_area('Unused MG24 right GPIO contacts',
    [(68,54.6),(70,54.6),(70,64.4),(68,64.4)],[p.F_Cu])

zone=p.ZONE(board);zone.SetLayer(p.B_Cu);zone.SetNet(netmap['GND']);zone.SetLocalClearance(mm(.2));zone.SetThermalReliefGap(mm(.25));zone.SetThermalReliefSpokeWidth(mm(.3))
poly=zone.Outline();poly.NewOutline()
for x,y in [(49.3,50.3),(78.7,50.3),(78.7,91.7),(49.3,91.7)]:poly.Append(mm(x),mm(y))
board.Add(zone)

settings=board.GetDesignSettings()
settings.m_MinClearance=mm(.127);settings.m_TrackMinWidth=mm(.15)
settings.m_CopperEdgeClearance=mm(.3);settings.m_HoleToHoleMin=mm(.25)
settings.m_SilkClearance=mm(.1);settings.m_MinSilkTextHeight=mm(.65)
settings.m_MinSilkTextThickness=mm(.1)
# Preserve the existing carrier's board origin and component placement datum.
translation = xy(87.9, 28.4)
for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings(), *board.Zones()]:
    item.Move(translation)
p.SaveBoard(str(ROOT/(NAME+'.kicad_pcb')),board)
pcb=ROOT/(NAME+'.kicad_pcb')

project={
 'meta':{'filename':NAME+'.kicad_pro','version':1},
 'board':{'design_settings':{'rules':{'min_clearance':.127,'min_track_width':.15,'min_copper_edge_clearance':.3,'min_hole_clearance':.2,'min_hole_to_hole':.25,'min_through_hole_diameter':.3,'min_via_diameter':.6,'min_via_annular_width':.15,'min_silk_clearance':.1,'min_text_height':.65,'min_text_thickness':.1},'defaults':{'board_outline_line_width':.05,'copper_line_width':.25},'drc_exclusions':[]}},
 'net_settings':{'classes':[{'name':'Default','clearance':.127,'track_width':.25,'via_diameter':.6,'via_drill':.3,'microvia_diameter':.3,'microvia_drill':.1,'diff_pair_width':.2,'diff_pair_gap':.25,'diff_pair_via_gap':.25,'wire_width':6,'bus_width':12,'line_style':0}],'meta':{'version':3}},
 'text_variables':{'REVISION':'E'},
}
(ROOT/(NAME+'.kicad_pro')).write_text(json.dumps(project,indent=2)+'\n')
print('Generated',pcb)
