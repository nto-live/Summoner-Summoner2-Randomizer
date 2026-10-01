"""Can a gold +Give field hold a big number size-preservingly? A +Give: N paired with
+Messagebox: "Gold" is the gold-pickup amount. The number field is fixed width (digits only), so
we can only widen a value to MORE digits if the field already has them OR we right-pad... but we
cannot grow bytes. Measure: for each gold pickup, the current +Give digits and how many digits we
could write. Report the max value each gold field can hold at its current width. Read-only.
"""
import os
import re
import sys
from collections import Counter
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

# A gold pickup: +Give: N ... +Messagebox: "Gold" within a few bytes
pat = re.compile(rb'\+Give:\s*(\d+)\s*\r\n\+Messagebox:\s*"Gold"')
hits = list(pat.finditer(blob))
print(f"gold pickups (+Give N + Messagebox Gold): {len(hits)}")
widths = Counter()
for m in hits:
    digits = m.group(1)
    widths[len(digits)] += 1
print("\ncurrent gold +Give digit-widths:")
for w, c in sorted(widths.items()):
    print(f"  {w}-digit values: {c}  (max value at this width = {'9'*w})")

# how many could hold at least '1000' (4 digits) WITHOUT growing bytes?
can_1000 = sum(c for w, c in widths.items() if w >= 4)
print(f"\ngold fields already >= 4 digits (could hold 1000 as-is): {can_1000}")
print("note: a value with FEWER digits can be widened by consuming adjacent spaces only if the")
print("field is space-padded; +Give uses no padding, so we can only right-justify within existing")
print("width. Max gold without adding bytes = fill each field with 9s (e.g. 1->9, 2->99, 3->999).")

# show a few raw records to confirm there's no padding room
print("\nsample raw gold records:")
for m in hits[:6]:
    s = m.start()
    print("  ", blob[s:s+40].decode('latin-1','replace').replace("\r","\\r").replace("\n","\\n"))
