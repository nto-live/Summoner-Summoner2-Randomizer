"""Q4 risk check: does door_name_shuffle (regex $Door:"...") put the invis-door02
record in scope, and could it rename it?

door_name_shuffle shuffles $Door names among EQUAL-LENGTH names. If invis-door02 (12
chars) shares its length class with other $Door names, the shuffle can rename it — and
the ELF's remove_object("invis-door02") would then no longer match the renamed record.

READ-ONLY.
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

with ISO.open("rb") as fh:
    bases = rc.find_all_vpps_cached(fh, ISO)
    _b, tb = rc.pick_tables(fh, bases)
    blob = tb.blob()

hits = list(re.finditer(rb'\$Door:\s*"([^"]+)"', blob))
by_len = defaultdict(list)
for m in hits:
    by_len[len(m.group(1))].append(m.group(1).decode("latin-1"))

print(f"total $Door name occurrences: {len(hits)}")
print("length classes (len -> count distinct / count total):")
for ln in sorted(by_len):
    vals = by_len[ln]
    distinct = sorted(set(vals))
    tag = ""
    if ln == len("invis-door02"):
        tag = "   <-- invis-door0N length class"
    print(f"  len {ln:2}: {len(vals):3} occurrences, {len(distinct):3} distinct{tag}")

INV = "invis-door02"
same_len = sorted(set(by_len[len(INV)]))
print(f'\nnames sharing invis-door02 length ({len(INV)}): {len(same_len)} distinct')
for nm in same_len:
    print("   ", nm)

# Would a shuffle actually move invis-door02? It moves if its length class has >=2
# distinct names. Count how many of each invis-door appear and what else shares length.
print("\nRISK VERDICT:")
n_class = len(same_len)
if n_class >= 2:
    print(f"  door_name_shuffle CAN rename invis-door02: its 12-char length class has "
          f"{n_class} distinct names, so the shuffle permutes them.")
else:
    print("  invis-door02 is alone in its length class; shuffle cannot change it.")
