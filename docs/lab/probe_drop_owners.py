"""Where do +Drop records attach, and do any MASAD-safe creatures carry drops? +Drop lives in
placement/attack records, not creature defs. Find: for each +Drop, the nearest preceding
$Character (the owning creature) - so we know which creatures drop loot. Cross with masad's loaded
hostiles (Orenian Soldier/Scout/Archer/Barbarian). If a masad-safe creature already drops, great;
if not, the honest options are limited. Also count how big drop lists get (max loot per enemy).
Read-only.
"""
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)

# For each +Drop, find owning creature (nearest preceding $Character within the same record block)
drops_by_creature = defaultdict(list)
for m in re.finditer(rb'\+Drop:\s*"([^"]+)"(?:\s+(\d+))?', blob):
    item = m.group(1).decode('latin-1')
    back = blob[max(0, m.start()-600):m.start()]
    cm = None
    for cc in re.finditer(rb'\$Character\s*:\s*"([^"]+)"', back):
        cm = cc
    owner = cm.group(1).decode('latin-1') if cm else "?"
    drops_by_creature[owner].append(item)

print("=== creatures with the most drops ===")
for owner, items in sorted(drops_by_creature.items(), key=lambda kv: -len(kv[1]))[:15]:
    print(f"  {owner:22} {len(items)} drop(s): {items[:4]}")

masad_safe = {"Orenian Soldier1","Orenian Soldier2","Orenian Archer","Orenian Scout","Barbarian Fighter"}
print("\n=== do masad-safe creatures carry drops? ===")
for c in masad_safe:
    print(f"  {c:20} drops={len(drops_by_creature.get(c, []))}")

# which drop-carrying creatures have SHORT names (<= an Orenian Soldier1 width 16) so we could swap
# a masad NPC -> a drop-rich creature that is also likely model-light? (informational)
print("\n=== drop-rich creatures with name<=16 (swap candidates, model-safety still unknown) ===")
for owner, items in sorted(drops_by_creature.items(), key=lambda kv:-len(kv[1])):
    if owner != "?" and len(owner) <= 16 and len(items) >= 2:
        print(f"  [{len(owner):2}] {owner:18} {len(items)} drops")
