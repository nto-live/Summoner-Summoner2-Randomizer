import os, re, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    vpp = rc.VppFile(f, t.base)
    blob = vpp.blob()

boss_members = ["IonaExt02_v2_script.tbl","jadetemple_v2_script.tbl","khosanilab2_script.tbl",
 "khosanilab_script.tbl","masad_script.tbl","Rand-Forest01_v2_script.tbl",
 "Rand-Forestnite1_v2_script.tbl","rand-hills01_v2_script.tbl","sewerboss_script.tbl",
 "TempleInt2_script.tbl","TempleInt_v2_script.tbl"]

def to_level(member):
    n = member
    for suf in ("_script.tbl",".tbl"):
        if n.endswith(suf): n = n[:-len(suf)]
    n = re.sub(r"_v\d+$","", n)
    return n

# door target names + level_scripts.json level set for reconciliation
targets = {x.lower() for x in rc.DOOR_TARGET_NAMES} if hasattr(rc,"DOOR_TARGET_NAMES") else set()
LS = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)),"level_scripts.json"))
lvlset=set()
if LS.is_file():
    import json
    d=json.loads(LS.read_text("utf-8"))
    lvlset={k.lower() for k in d.get("levels",{})}

print(f"DOOR_TARGET_NAMES available: {bool(targets)} ({len(targets)}) ; level_scripts levels: {len(lvlset)}")
print("\nmember -> level name  | in door targets? | in level_scripts?")
for m in boss_members:
    lv = to_level(m)
    print(f"  {m:34} -> {lv:22} door={lv.lower() in targets}  lvlscripts={lv.lower() in lvlset}")

# Also: does each boss member carry an inline $Level: or Level_info naming itself? check near its start
print("\n=== inline self-name token inside each boss member (first 2000 bytes) ===")
cum=0; spans=[]
for e in vpp.entries:
    spans.append((cum, cum+e.size, e.name)); cum+=e.size
for m in boss_members:
    span=[s for s in spans if s[2]==m][0]
    seg=blob[span[0]:span[0]+2500]
    toks=re.findall(rb'\$Level:\s*"([^"]+)"|Level_info\s*"([^"]+)"|Level file for ([^\r\n*]+)', seg)
    flat=[ (a or b or c).decode("latin-1") for a,b,c in toks ][:4]
    print(f"  {m:34} inline: {flat}")
