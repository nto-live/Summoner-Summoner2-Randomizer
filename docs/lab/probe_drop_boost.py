"""Design a 'drops_boost': force every +Drop chance to 100 (guaranteed) and optionally rewrite the
item to a HIGH-LEVEL item of equal length. Report:
  1. how many +Drop records exist, their chance distribution
  2. high-level item names available by length (to swap in, equal-length)
  3. do existing transforms (enemy_drops_always / enemy_drops_random) already touch chance?
Read-only.
"""
import os, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    f.seek(t.base); blob=f.read(t.total_size)

drops=list(re.finditer(rb'(\+Drop:\s*")([^"]+)("\s+)(\d+)', blob))
print(f"+Drop records with a chance value: {len(drops)}")
chances=Counter(int(m.group(4)) for m in drops)
print("chance distribution:", dict(sorted(chances.items())))

# high-level items (heuristic: gear-sounding names) by length, from dropped + $Item universe
HIGH=["Midnight Platemail","Hellfire Necklace","Ring of the Night","Medallion of Night",
      "Elemental Necklace","Guardian Heater","Quilted Holy Robe","Battle Torque","Ring of Might"]
print("\nhigh-level candidate items by length:")
byw={}
for h in HIGH: byw.setdefault(len(h),[]).append(h)
for w in sorted(byw): print(f"   {w}: {byw[w]}")

# dropped-item name lengths (what widths we'd need high items for)
print("\ndropped item name widths (how many drops at each width):")
dw=Counter(len(m.group(2)) for m in drops)
for w,c in sorted(dw.items()): print(f"   w={w:2}: {c} drops")

# existing transform check
print("\nenemy_drops_always exists:", "enemy_drops_always" in rc.TRANSFORMS)
print("enemy_drops_random exists:", "enemy_drops_random" in rc.TRANSFORMS)
