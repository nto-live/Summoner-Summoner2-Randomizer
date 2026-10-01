"""TempleInt as a boss room: it owns 5 bosses (Luminar, Machival, Pyrul, Tiger Rider, Titus) and
has 30 clean slots. For a SAFE aggro fill we need clean (non-pacified) NPC slots whose name width
EXACTLY equals an owned boss name width (no padding). Count the equal-length matches by width, and
list how many bosses we can actually place. Also: how is TempleInt reached (its doors / what points
at it) so we can chain INTO it. Read-only.
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
own=[]
for s,e in rc._placement_records(blob):
    seg=blob[s:e]
    if b"+Boss" in seg and lvl_at(s)==TGT:
        cm=rc.PLACEMENT_CHAR_RE.search(seg)
        if cm: own.append(cm.group(2))
own=sorted(set(own))
print("TempleInt owned bosses + widths:", [(b.decode(), len(b)) for b in own])
boss_w={len(b) for b in own}

_m,peaceful=rc._analyse_enemies(blob)
clean=[]; dirty=0
for r in peaceful:
    if lvl_at(r['start'])!=TGT: continue
    if any(p in blob[r['start']:r['end']] for p in PAC): dirty+=1; continue
    clean.append(r)
from collections import Counter
cw=Counter(len(r['char']) for r in clean)
print(f"\nTempleInt clean slots: {len(clean)} (pacified skipped: {dirty})")
print("clean slot widths:", dict(sorted(cw.items())))
match=sum(c for w,c in cw.items() if w in boss_w)
print(f"clean slots whose width == an owned-boss width (placeable, no padding): {match}")
for w in sorted(boss_w):
    print(f"   width {w}: bosses={[b.decode() for b in own if len(b)==w]}  clean_slots={cw.get(w,0)}")

# how is TempleInt reached?
print("\n=== doors that point AT TempleInt (how to chain into it) ===")
for r in rc._door_records(blob):
    if rc._door_key(r['name'])==rc._door_key("TempleInt"):
        print(f"   from {lvl_at(r['off']):16} idx={r['index']} script={int(r['has_script'])}")
print("\n=== TempleInt's own doors (where it can send you next) ===")
for r in rc._door_records(blob):
    if rc._door_key(lvl_at(r['off']))==rc._door_key("TempleInt"):
        print(f"   dest={r['name'].decode('latin-1'):16} idx={r['index']} script={int(r['has_script'])}")
