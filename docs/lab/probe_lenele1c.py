"""Can lenele1c (the 'temple outskirts', TempleInt's door target) be boss room 2? Check:
  - hostile creatures it already LOADS (placements) + widths (model-safe fills)
  - clean (non-pacified) slot widths
  - intersection = model-safe aggro fills (equal-length)
Also do the same recheck for TempleInt but allow fills from ANY hostile TempleInt loads (not just
+Boss), since its bosses are hidden. Read-only.
"""
import os, re, sys, bisect
from pathlib import Path
from collections import Counter
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
team={}
for m in re.finditer(rb'#Character Info', blob):
    seg=blob[m.start():m.start()+400]
    cm=re.search(rb'\$Character\s*:\s*"([^"]+)"',seg); tm=re.search(rb'\$Team\s*:\s*"([^"]+)"',seg)
    if cm and tm: team[cm.group(1)]=tm.group(1).decode()

def analyze(TGT):
    loaded=set()
    for s,e in rc._placement_records(blob):
        if lvl_at(s)!=TGT: continue
        cm=rc.PLACEMENT_CHAR_RE.search(blob[s:e])
        if cm: loaded.add(cm.group(1))
    hostile={c for c in loaded if team.get(c) in ('hostile','evil')}
    _m,peaceful=rc._analyse_enemies(blob)
    cw=Counter(); clean=[]
    for r in peaceful:
        if lvl_at(r['start'])!=TGT: continue
        if any(p in blob[r['start']:r['end']] for p in PAC): continue
        cw[len(r['char'])]+=1; clean.append(r)
    print(f"\n=== {TGT} ===")
    print("  hostile loaded:", sorted(c.decode() for c in hostile))
    print("  clean slot widths:", dict(sorted(cw.items())))
    total=0
    for w,c in sorted(cw.items()):
        cands=[x.decode() for x in hostile if len(x)==w]
        if cands:
            print(f"    width {w}: slots={c} -> {cands}")
            total+=c
    print(f"  model-safe aggro fills: {total}")

analyze("TempleInt")
analyze("lenele1c")
