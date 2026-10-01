"""Pick chain rooms that render on arrival (avoid the black-screen ones). For each level that owns
bosses AND has clean EQUAL-LENGTH slots, report: is it +Script-safe (self-initializing name=script),
is it an overworld-type (worldmap doors), and does masad/other rooms legally reach it. We want
self-initializing, non-mid-story rooms. Exclude sewerboss (loaded black). Read-only.
"""
import os
import re
import sys
import bisect
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
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

PAC=(b"+Hidden",b'"turn hostile"\t0',b'"wait for go"',b'"show/hide"\t0')
own_bosses={}
for s,e in rc._placement_records(blob):
    seg=blob[s:e]
    if b"+Boss" not in seg: continue
    cm=rc.PLACEMENT_CHAR_RE.search(seg); lv=lvl_at(s)
    if cm and lv: own_bosses.setdefault(rc._door_key(lv),[]).append(cm.group(2))
_m,peaceful=rc._analyse_enemies(blob)
clean={}
for r in peaceful:
    if any(p in blob[r['start']:r['end']] for p in PAC): continue
    lv=lvl_at(r['start'])
    if lv: clean.setdefault(rc._door_key(lv),[]).append(r)
safe=rc._no_script_safe_targets(blob)
slots=rc._level_start_slots(blob)
recs=rc._door_records(blob)
doors={}
for r in recs: doors.setdefault(rc._door_key(lvl_at(r['off'])),[]).append(r)
keyname={}
for n,s,e in [(vpp.entries[i].name, cum[i], cum[i]+vpp.entries[i].size) for i in range(len(vpp.entries))]:
    nn=n
    for suf in ("_script.tbl",".tbl"):
        if nn.lower().endswith(suf): nn=nn[:-len(suf)]; break
    nn=re.sub(r"_v\d+$","",nn); keyname.setdefault(rc._door_key(nn),nn)

print("=== boss rooms: own-boss equal-len clean slots, script-safe, door types ===")
rooms=[]
for key,bosses in own_bosses.items():
    name=keyname.get(key,key)
    if name.lower()=="sewerboss":  # excluded: loaded black
        continue
    # equal-length clean slots that fit an owned boss
    fit=0
    for r in clean.get(key,[]):
        if any(len(b)==len(r['char']) for b in bosses): fit+=1
    if fit==0: continue
    dsts=[d['name'].decode('latin-1') for d in doors.get(key,[])]
    overworld = any(d.lower().startswith('worldmap') for d in dsts)
    rooms.append(key)
    print(f"  {name:14} fit_slots={fit:2} script_safe={rc._door_key(name) in safe} "
          f"overworld_doors={overworld} dests={dsts[:4]}")

def legal(a,b):
    for d in doors.get(rc._door_key(a),[]):
        dn=d['name'].decode('latin-1')
        if len(b)>len(dn): continue
        if d['index'] is not None and d['index'] not in slots.get(rc._door_key(b),set()): continue
        if not d['has_script'] and rc._door_key(b) not in safe: continue
        return d
    return None

print("\n=== chain from masad through these rooms (sewerboss excluded) ===")
rem=[r for r in rooms]
import random
rng=random.Random("ROOMS2")
rng.shuffle(rem)
chain=["masad"]; cur="masad"
while rem:
    nxt=next((r for r in rem if legal(cur, keyname[r])), None)
    if not nxt: break
    chain.append(keyname[nxt]); rem.remove(nxt); cur=keyname[nxt]
print("  ", " -> ".join(chain))
