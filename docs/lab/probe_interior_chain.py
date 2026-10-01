"""Chain boss rooms via INTERIOR doors (not worldmap, not the mid-story sewer) which are more
likely to render on arrival. For each boss-owning level with equal-length clean slots, list its
doors with type, and find a chain among them using only interior-style links. We relax 'own boss
only' to 'owns a boss that fits' but keep equal-length + clean. Report door dest + whether it's a
plausibly-safe interior transition. Read-only.
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
own={}
for s,e in rc._placement_records(blob):
    seg=blob[s:e]
    if b"+Boss" in seg:
        cm=rc.PLACEMENT_CHAR_RE.search(seg); lv=lvl_at(s)
        if cm and lv: own.setdefault(rc._door_key(lv),set()).add(cm.group(2))
_m,peaceful=rc._analyse_enemies(blob)
clean={}
for r in peaceful:
    if any(p in blob[r['start']:r['end']] for p in PAC): continue
    clean.setdefault(rc._door_key(lvl_at(r['start'])),[]).append(r)
safe=rc._no_script_safe_targets(blob); slots=rc._level_start_slots(blob)
recs=rc._door_records(blob); doors={}
for r in recs: doors.setdefault(rc._door_key(lvl_at(r['off'])),[]).append(r)
keyname={}
for i in range(len(vpp.entries)):
    nn=vpp.entries[i].name
    for suf in ("_script.tbl",".tbl"):
        if nn.lower().endswith(suf): nn=nn[:-len(suf)]; break
    nn=re.sub(r"_v\d+$","",nn); keyname.setdefault(rc._door_key(nn),nn)

# boss rooms with at least one equal-length clean slot for an owned boss
rooms=[]
for k,bs in own.items():
    if any(any(len(b)==len(r['char']) for b in bs) for r in clean.get(k,[])):
        rooms.append(k)
print("boss rooms with usable equal-len clean slots:", [keyname[k] for k in rooms])

# interior door = dest is a real level, NOT worldmap*, NOT sewer-family
def interior(dn): 
    d=dn.lower(); return not d.startswith("worldmap") and "sewer" not in d
print("\n=== doors (interior flagged) per boss room ===")
for k in rooms:
    ds=[(d['name'].decode('latin-1'), d['index'], int(d['has_script'])) for d in doors.get(k,[])]
    print(f"  {keyname[k]:14} {[ (n, 'INT' if interior(n) else 'ext') for n,_i,_s in ds]}")

def legal(a,b,interior_only=True):
    for d in doors.get(rc._door_key(a),[]):
        dn=d['name'].decode('latin-1')
        if interior_only and not interior(dn): continue
        if len(b)>len(dn): continue
        if d['index'] is not None and d['index'] not in slots.get(rc._door_key(b),set()): continue
        if not d['has_script'] and rc._door_key(b) not in safe: continue
        return d
    return None

# longest interior-only chain among rooms, reachable from masad (any door for the first hop)
nodes=rooms[:]
adj={a:[b for b in nodes if b!=a and legal(keyname[a],keyname[b])] for a in nodes}
best=[]
def dfs(n,vis,path):
    global best
    if len(path)>len(best): best=path[:]
    for m in adj[n]:
        if m not in vis: vis.add(m); path.append(m); dfs(m,vis,path); path.pop(); vis.remove(m)
for st in nodes: dfs(st,{st},[st])
print("\nlongest INTERIOR chain among boss rooms:", [keyname[k] for k in best])
print("masad reaches (interior-only):", [keyname[b] for b in nodes if legal('masad',keyname[b])])
