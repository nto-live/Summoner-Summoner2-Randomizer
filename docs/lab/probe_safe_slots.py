"""Which TempleInt NPC slots are SAFE to overwrite? The 'Med High Priest' swap froze because he's a
scripted DIALOGUE/scene NPC. A safe slot = a peaceful placement whose $Name is NOT referenced
elsewhere by a +Trigger, dialogue tag, $Character dialogue, or script action. Classify TempleInt's
clean slots into likely-safe (name appears only in its own placement) vs scene-critical (name
appears elsewhere too). Read-only.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    vpp=rc.VppFile(f,t.base); blob=vpp.blob()
cum=[]; a=0
for e in vpp.entries: cum.append(a); a+=e.size
def lvl_at(off):
    i=bisect.bisect_right(cum,off)-1
    n=vpp.entries[i].name if 0<=i<len(vpp.entries) else "?"
    for suf in ("_script.tbl",".tbl"):
        if n.lower().endswith(suf): n=n[:-len(suf)]; break
    return re.sub(r"_v\d+$","",n)
PAC=(b"+Hidden",b'"turn hostile"\t0',b'"wait for go"',b'"show/hide"\t0')

_m,peaceful=rc._analyse_enemies(blob)
# For TempleInt clean placements, get $Name and count how often that name appears in the WHOLE blob
print("=== TempleInt clean slots: $Name, $Character width, ref-count (safe if refs==1) ===")
safe=[]; scene=[]
for r in peaceful:
    if lvl_at(r['start'])!="TempleInt": continue
    seg=blob[r['start']:r['end']]
    if any(p in seg for p in PAC): continue
    nm=re.search(rb'\$Name\s*:\s*"([^"]+)"', seg)
    if not nm: continue
    name=nm.group(1)
    refs=len(re.findall(re.escape(name), blob))
    tag="SAFE" if refs<=1 else "scene-critical"
    (safe if refs<=1 else scene).append((name.decode('latin-1'), len(r['char']), refs))
print(f"\nSAFE slots (name referenced only by its own placement): {len(safe)}")
for n,w,refs in safe[:30]:
    print(f"   {n:26} charW={w} refs={refs}")
print(f"\nscene-critical (referenced elsewhere - DO NOT overwrite): {len(scene)}")
for n,w,refs in scene[:15]:
    print(f"   {n:26} charW={w} refs={refs}")
