"""What loot do masad's enemies actually have, and what gold is in masad? Diagnose why no drops/gold
were seen. Check:
  1. do masad's hostile creatures (Orenian Soldier/Scout etc) have ANY +Drop entries in their defs?
     (enemy_drops_random only shuffles existing drops; enemy_drops_always guarantees them - but only
      if drops EXIST.)
  2. how many gold container pickups (+Give N + Messagebox Gold) are IN masad specifically?
  3. can we ADD drops? (probably not size-preservingly). What's the honest max loot lever?
Read-only.
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
cum = []; acc = 0
for e in vpp.entries:
    cum.append(acc); acc += e.size
def lvl_at(off):
    i = bisect.bisect_right(cum, off) - 1
    n = vpp.entries[i].name if 0 <= i < len(vpp.entries) else "?"
    for suf in ("_script.tbl", ".tbl"):
        if n.lower().endswith(suf):
            n = n[:-len(suf)]; break
    return re.sub(r"_v\d+$", "", n)

# 1. do the masad hostile creatures have +Drop in their #Character Info defs?
print("=== +Drop entries in hostile creature defs (overall) ===")
drop_defs = 0
for m in re.finditer(rb'#Character Info', blob):
    seg = blob[m.start():m.start()+500]
    if b"+Drop" in seg:
        drop_defs += 1
print(f"  creature defs with +Drop: {drop_defs}")
# where do +Drop records actually live - are they per-creature or per-placement?
print("\n  sample +Drop with 40 bytes context:")
for m in list(re.finditer(rb'\+Drop:[^\r\n]{0,40}', blob))[:6]:
    s = m.start()
    print("   ", blob[s-30:s+30].decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))

# which creatures carry drops? name near each +Drop
print("\n=== creatures that have +Drop (sample names) ===")
seen=set()
for m in re.finditer(rb'\+Drop:\s*"[^"]+"', blob):
    back = blob[max(0,m.start()-300):m.start()]
    cm = None
    for cc in re.finditer(rb'\$Character\s*:\s*"([^"]+)"', back):
        cm = cc
    if cm:
        nm = cm.group(1).decode('latin-1')
        if nm not in seen:
            seen.add(nm)
            if len(seen)<=15:
                print(f"   {nm}")

# 2. gold containers in masad
print("\n=== gold containers (+Give N + Messagebox Gold) and their level ===")
gold = list(re.finditer(rb'\+Give:\s*(\d+)\s*\r\n\+Messagebox:\s*"Gold"', blob))
by_lvl={}
for m in gold:
    by_lvl.setdefault(lvl_at(m.start()),[]).append(m.group(1).decode())
for lv,vals in by_lvl.items():
    print(f"   {lv:16} {vals}")
