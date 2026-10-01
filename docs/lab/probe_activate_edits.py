"""Pin down the exact size-preserving edits to make bosses live on arrival.

Mechanism: a boss record has +Hidden (invisible until unhidden) and an +Action list with
"wait for go" (blocks until a scripted trigger fires). To make the boss appear and engage on
entry we need, per boss record:
  - neutralize "+Hidden" so the boss is visible (can we blank/flip it size-preservingly? what's the
    exact token + surrounding bytes?)
  - neutralize "wait for go" so the action sequence doesn't block (replace with a same-length no-op
    action, or with 'turn hostile' 1?)

This probe dumps every boss record's +Hidden presence and full +Action list with exact bytes +
lengths, so we can design in-place same-length replacements. Also test candidate same-length
no-op action strings. Read-only.
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

# distinct action command strings and their lengths (to find same-length no-ops)
print("=== distinct +Action command strings (len) across boss records ===")
from collections import Counter
acts = Counter()
hidden = 0
nrec = 0
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    nrec += 1
    if b"+Hidden" in seg:
        hidden += 1
    for m in re.finditer(rb'\+Action:\s*"([^"]+)"(\s*\d+)?', seg):
        acts[(m.group(1).decode('latin-1'), len(m.group(1)))] += 1
print(f"{nrec} boss records; {hidden} carry +Hidden")
for (name, ln), c in acts.most_common():
    print(f"  x{c:3} len={ln:2}  {name!r}")

# exact bytes: show +Hidden in context and a full action list
print("\n=== +Hidden in context (first 3 boss records that have it) ===")
shown = 0
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" in seg and b"+Hidden" in seg:
        i = seg.find(b"+Hidden")
        print(f"  ...{seg[i-20:i+20]!r}...")
        shown += 1
        if shown >= 3:
            break

# what is the exact 'wait for go' action line (so a same-length replacement can be designed)
print("\n=== 'wait for go' exact line bytes ===")
m = re.search(rb'\+Action:\s*"wait for go"', blob)
print("  ", repr(blob[m.start():m.start()+30]))
print("  len of 'wait for go' =", len(b"wait for go"))
# candidate same-length (11 char) action replacements that are harmless/complete-immediately:
for cand in (b"wait at   X", b"do nothing!", b"turn hostil"):
    print(f"    candidate 11-char: {cand!r} (len {len(cand)})")
