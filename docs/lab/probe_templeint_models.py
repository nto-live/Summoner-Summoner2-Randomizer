"""TempleInt clean slots are wide (12/15/16/19/22/23); its own bosses are short (5-11) so none fit
equal-length. BUT any HOSTILE creature whose model TempleInt already loads AND whose name width
matches a clean slot is a valid, model-safe, aggro fill. Find every creature TempleInt loads (its
+Monster placements + its +Boss) and their widths, and intersect with the clean-slot widths.
Read-only.
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
PAC=(b"+Hidden",b'"turn hostile"\t0',b'"wait for go"',b'"show/hide"\t0')
TGT="TempleInt"

# team lookup
team={}
for m in re.finditer(rb'#Character Info', blob):
    seg=blob[m.start():m.start()+400]
    cm=re.search(rb'\$Character\s*:\s*"([^"]+)"',seg); tm=re.search(rb'\$Team\s*:\s*"([^"]+)"',seg)
    if cm and tm: team[cm.group(1)]=tm.group(1).decode()

# creatures TempleInt loads: any placement (monster, boss, or even NPC char) in TempleInt
loaded=set()
for s,e in rc._placement_records(blob):
    if lvl_at(s)!=TGT: continue
    cm=rc.PLACEMENT_CHAR_RE.search(blob[s:e])
    if cm: loaded.add(cm.group(1))
hostile_loaded = {c for c in loaded if team.get(c) in ('hostile','evil')}
print("hostile creatures TempleInt already loads:", sorted(c.decode() for c in hostile_loaded))

# clean slot widths in TempleInt
_m,peaceful=rc._analyse_enemies(blob)
from collections import Counter
cw=Counter()
clean_recs=[]
for r in peaceful:
    if lvl_at(r['start'])!=TGT: continue
    if any(p in blob[r['start']:r['end']] for p in PAC): continue
    cw[len(r['char'])]+=1; clean_recs.append(r)
print("clean slot widths:", dict(sorted(cw.items())))

print("\n=== model-safe aggro fills (hostile TempleInt-loaded creature == clean slot width) ===")
total=0
for w,c in sorted(cw.items()):
    cands=[x.decode() for x in hostile_loaded if len(x)==w]
    print(f"  width {w}: slots={c} fillable_with={cands}")
    if cands: total+=c
print(f"\nTOTAL model-safe aggro fills in TempleInt: {total}")
