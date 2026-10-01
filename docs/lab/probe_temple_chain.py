"""Chain masad -> TempleInt -> one more boss room. Resolve:
  1. can masad legally reach TempleInt? (door in masad whose field fits 'TempleInt', slot, script)
  2. TempleInt's own doors -> where can its FRONT door legally go that is another boss-owning level?
Report legal targets for each hop so we can pick the 3-level chain. Read-only.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    vpp = rc.VppFile(f, t.base); blob = vpp.blob()
cum=[]; acc=0
for e in vpp.entries: cum.append(acc); acc+=e.size
def lvl_at(off):
    i=bisect.bisect_right(cum,off)-1
    n=vpp.entries[i].name if 0<=i<len(vpp.entries) else "?"
    for suf in ("_script.tbl",".tbl"):
        if n.lower().endswith(suf): n=n[:-len(suf)]; break
    return re.sub(r"_v\d+$","",n)

own=set()
for s,e in rc._placement_records(blob):
    if b"+Boss" in blob[s:e]: own.add(rc._door_key(lvl_at(s)))

safe=rc._no_script_safe_targets(blob); slots=rc._level_start_slots(blob)
recs=rc._door_records(blob); doors={}
for r in recs: doors.setdefault(rc._door_key(lvl_at(r['off'])),[]).append(r)
keyname={}
for i in range(len(vpp.entries)):
    nn=vpp.entries[i].name
    for suf in ("_script.tbl",".tbl"):
        if nn.lower().endswith(suf): nn=nn[:-len(suf)]; break
    nn=re.sub(r"_v\d+$","",nn); keyname.setdefault(rc._door_key(nn),nn)

def door_can(frm_key, to_name):
    for d in doors.get(frm_key,[]):
        dn=d['name'].decode('latin-1')
        if len(to_name)>len(dn): continue
        if d['index'] is not None and d['index'] not in slots.get(rc._door_key(to_name),set()): continue
        if not d['has_script'] and rc._door_key(to_name) not in safe: continue
        return d
    return None

print("masad doors:", [(d['name'].decode('latin-1'), d['index'], int(d['has_script'])) for d in doors.get('masad',[])])
print("masad -> TempleInt:", "OK" if door_can('masad','TempleInt') else "NO (field too narrow / slot / script)")
print("\nTempleInt doors:", [(d['name'].decode('latin-1'), d['index'], int(d['has_script'])) for d in doors.get(rc._door_key('TempleInt'),[])])
print("TempleInt can legally reach these boss-owning levels:")
for k in own:
    if k==rc._door_key('TempleInt'): continue
    if door_can(rc._door_key('TempleInt'), keyname[k]):
        print("   ", keyname[k])
# also: who can reach TempleInt (if masad can't directly, maybe via a 1st hop)
print("\nlevels that can legally reach TempleInt:")
for frm in doors:
    if door_can(frm, 'TempleInt'):
        print("   ", keyname.get(frm, frm))
