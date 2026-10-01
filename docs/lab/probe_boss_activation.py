"""How is a BOSS encounter activated? boss_rush only MOVES the placement; the boss may still need a
scripted trigger to spawn/wake (like the fire barrier needed a dialogue flag). Examine the full
record around several +Boss placements: what +Action / trigger / flag / 'wait for go' / show-hide
drives them, and whether moving the $Start position alone would ever show the boss. Read-only.
"""
import os
import re
import sys
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

n = 0
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    print(f"\n=== boss {ch.group(1).decode() if ch else '?'} @ {s:#x} (full record) ===")
    print(seg.decode('latin-1', 'replace').replace('\r', '\\r').replace('\n', '\\n')[:600])
    n += 1
    if n >= 5:
        break

# how do +Boss records relate to 'wait for go' / triggers / activation flags?
print("\n\n=== tokens co-occurring in boss records (first 11 boss records) ===")
from collections import Counter
toks = Counter()
cnt = 0
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    for m in re.finditer(rb'[\+\$][A-Za-z][A-Za-z0-9 _]{1,20}', seg):
        toks[m.group(0)] += 1
    cnt += 1
for tk, c in toks.most_common(25):
    print(f"  {c:3}  {tk.decode('latin-1')}")
