"""Verify t_door_name_shuffle now PINS invis-door0N across many seeds.

For each seed: run the transform on the real TABLES script blob, then confirm the three pinned
names are still present at the SAME byte offsets they started at (i.e. not renamed, not moved), and
that the transform still shuffled other doors (rep.changed > 0). Read-only wrt the ISO.
"""
import os
import re
import sys
from pathlib import Path
from random import Random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)

pat = rb'\$Door:\s*"([^"]+)"'
pinned = rc.ENGINE_PINNED_DOOR_NAMES

# baseline positions of the pinned names
base_pos = {}
for m in re.finditer(pat, blob):
    if m.group(1) in pinned:
        base_pos.setdefault(m.group(1), []).append((m.start(1), m.end(1)))
print("pinned names present at baseline:")
for n, ps in base_pos.items():
    print(f"  {n.decode()}: {len(ps)} record(s)")

all_ok = True
for seed in ["A", "B", "C", "SEED123", "everything", "door", "xyz", "42"]:
    out, rep = rc.t_door_name_shuffle(blob, Random(seed))
    # every pinned name must sit at exactly its baseline byte range with its original bytes
    for n, ps in base_pos.items():
        for (s, e) in ps:
            if out[s:e] != n:
                all_ok = False
                print(f"  FAIL seed={seed}: {n.decode()} at [{s:#x}] became {out[s:e]!r}")
    # sanity: something else still shuffled
    tag = "changed>0" if rep.changed > 0 else "NO CHANGES(!)"
    print(f"  seed={seed:9} changed={rep.changed:4} {tag}  notes={rep.notes}")

print("\nRESULT:", "PASS - all pinned doors held in place across seeds" if all_ok else "FAIL")
