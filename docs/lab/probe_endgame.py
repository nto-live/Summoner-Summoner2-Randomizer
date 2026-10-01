"""Can TempleInt's exit lead to 'endgame'? Check:
  1. is 'endgame' a real Level_info / door-target name, and its name width (fits TempleInt's door?)
  2. is it script-safe or on the exclude list (why)?
  3. who normally has a door to endgame, with what +Index/+Script (so we copy a WORKING arrival)?
  4. what gates the ending (endgame_gate binary patch @0x00212274 - gamestage threshold)?
Read-only.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    f.seek(t.base); blob=f.read(t.total_size)

print("endgame in DOOR_TARGET_NAMES:", any(n.lower()=="endgame" for n in rc.DOOR_TARGET_NAMES))
print("DOOR_TARGET_EXCLUDE:", getattr(rc, "DOOR_TARGET_EXCLUDE", "n/a"))
safe=rc._no_script_safe_targets(blob)
print("endgame in no-script-safe set:", rc._door_key("endgame") in safe)
slots=rc._level_start_slots(blob)
print("endgame start slots:", slots.get(rc._door_key("endgame")))

# any door that already points at endgame (a known-good arrival to copy)?
print("\n=== existing doors -> endgame (name/idx/script) ===")
for r in rc._door_records(blob):
    if rc._door_key(r['name'])==rc._door_key("endgame"):
        print(f"   dest={r['name'].decode('latin-1')!r} idx={r['index']} script={int(r['has_script'])}")

# endgame as a level name anywhere + context
print("\n=== 'endgame' occurrences ===")
for m in list(re.finditer(rb'endgame', blob, re.I))[:8]:
    print("   ", blob[max(0,m.start()-30):m.start()+20].decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))

# TempleInt's door width (can it hold 'endgame' = 7 chars?)
import bisect
cum=[]; acc=0
# need vpp member ranges; quick reload
info2=discover.identify(str(ISO)); t2=discover.find_tables(info2.vpps)
with open(ISO,"rb") as f:
    vpp=rc.VppFile(f,t2.base)
cum=[]; a=0
for e in vpp.entries: cum.append(a); a+=e.size
def lvl_at(off):
    i=bisect.bisect_right(cum,off)-1
    n=vpp.entries[i].name if 0<=i<len(vpp.entries) else "?"
    for suf in ("_script.tbl",".tbl"):
        if n.lower().endswith(suf): n=n[:-len(suf)]; break
    return re.sub(r"_v\d+$","",n)
blob2=vpp.blob()
print("\n=== TempleInt door (can it hold 'endgame' len 7?) ===")
for r in rc._door_records(blob2):
    if rc._door_key(lvl_at(r['off']))==rc._door_key("TempleInt"):
        print(f"   dest={r['name'].decode('latin-1')!r} (w={len(r['name'])}) idx={r['index']} script={int(r['has_script'])}")
