"""Verify the new door_destination_remap `scope` option: interior / overworld / all.

Runs the transform on the real script blob at each scope and prints how many doors it changed and
the eligibility note, confirming: interior (safe, current behavior) < all, and interior + overworld
account for the full door set. Read-only wrt the ISO.
"""
import os
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

for scope in ("interior", "overworld", "all"):
    out, rep = rc.t_door_destination_remap(blob, Random("SCOPE"), how="shuffle", scope=scope)
    print(f"\n=== scope={scope} ===")
    print(f"  changed={rep.changed}, size preserved={len(out) == len(blob)}")
    for n in rep.notes:
        print(f"    - {n}")

# bad scope must refuse
_, rep = rc.t_door_destination_remap(blob, Random("x"), scope="bogus")
print("\nbad scope refused:", "changed=0" if rep.changed == 0 else "FAIL", "|", rep.notes[0])
