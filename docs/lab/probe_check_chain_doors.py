"""What do the boss_rooms chained doors ACTUALLY point to in the built ISO, and is the black
'palace aqueduct' level one of our hops or a vanilla door? Read the BUILT disc's door records in the
chain levels and show their destinations. Read-only on the OUTPUT iso.
"""
import os
import re
import sys
import bisect
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\out\Summoner-BOSSROOMS.iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    vpp = rc.VppFile(f, t.base)
    blob = vpp.blob()
cum=[]; acc=0
for e in vpp.entries:
    cum.append(acc); acc+=e.size
def lvl_at(off):
    i=bisect.bisect_right(cum,off)-1
    n=vpp.entries[i].name if 0<=i<len(vpp.entries) else "?"
    for suf in ("_script.tbl",".tbl"):
        if n.lower().endswith(suf): n=n[:-len(suf)]; break
    return re.sub(r"_v\d+$","",n)

for lv in ("masad","sewerboss","IonaExt02"):
    print(f"\n=== doors in {lv} (built disc) ===")
    for r in rc._door_records(blob):
        if rc._door_key(lvl_at(r['off']))==rc._door_key(lv):
            print(f"   dest={r['name'].decode('latin-1'):16} idx={r['index']} script={int(r['has_script'])}")
