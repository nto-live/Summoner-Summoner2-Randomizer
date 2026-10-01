"""Do the BOSSES we place carry +Drop lists? If so, a room full of them drops loot. Find +Drop
records whose owning creature is one of our boss names. Also list which creatures DO have drops +
counts, so if bosses lack drops we know which drop-rich creatures we could use instead (model
permitting). Read-only.
"""
import os, re, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    f.seek(t.base); blob=f.read(t.total_size)

drops=defaultdict(list)
for m in re.finditer(rb'\+Drop:\s*"([^"]+)"(?:\s+(\d+))?', blob):
    back=blob[max(0,m.start()-500):m.start()]
    cm=None
    for cc in re.finditer(rb'\$Character\s*:\s*"([^"]+)"', back): cm=cc
    if cm: drops[cm.group(1).decode('latin-1')].append(m.group(1).decode('latin-1'))

BOSSES=["Luminar","Pyrul","Titus","Machival","Tiger Rider","Phoenix Rider","Serpent Rider",
        "Ghost Rider","Giant Salamanka","Tentacle Beast","Evil Urath","Evil Joseph"]
print("=== do our bosses carry drops? ===")
for b in BOSSES:
    print(f"  {b:16} drops={drops.get(b, [])}")

print("\n=== creatures WITH drops (name, count, items) - potential loot enemies ===")
for owner,items in sorted(drops.items(), key=lambda kv:-len(kv[1]))[:20]:
    print(f"  [{len(owner):2}] {owner:20} x{len(items)}: {items[:4]}")
