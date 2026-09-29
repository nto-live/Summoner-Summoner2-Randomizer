"""Examine +Messagebox records: are they the tutorial popup text, and how are they keyed?

We want to blank ONLY tutorial popups (leave real messageboxes alone if any are gameplay-critical).
Show the full structure of +Messagebox entries and whether any reference a tutorial flag / masad.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)


def show(pos, before=40, after=240):
    s = max(0, pos - before)
    seg = blob[s:pos + after].decode("latin-1", "replace")
    return seg.replace("\r", "\\r").replace("\n", "\\n")


hits = list(re.finditer(rb'\+Messagebox', blob))
print(f"+Messagebox count: {len(hits)}\n")

print("=== first 8 +Messagebox records (raw structure) ===")
for m in hits[:8]:
    print(f"@{m.start():#010x}: {show(m.start())}")
    print()

# Where do the masad tutorial popups live? The step machine fires them; look for a block that
# pairs a tutorial-ish key with message text. Search for 'masad' near +Messagebox.
print("=== +Messagebox entries whose following 400 bytes mention 'tutorial' or 'masad' ===")
n = 0
for m in hits:
    window = blob[m.start():m.start() + 400]
    if b"tutorial" in window or b"masad" in window:
        print(f"@{m.start():#010x}: {show(m.start(), 20, 360)}")
        print()
        n += 1
        if n >= 8:
            break
if n == 0:
    print("  (none — messageboxes are not co-located with tutorial keys)")

# What field carries the actual words inside a +Messagebox? Look at the token right after it.
print("=== tokens that immediately follow +Messagebox ===")
from collections import Counter
follow = Counter()
for m in hits:
    tail = blob[m.end():m.end() + 60]
    mm = re.match(rb'[:\s"{]*([#\+\$][A-Za-z][A-Za-z0-9 _]{0,24}|")', tail)
    follow[mm.group(0).decode("latin-1").strip() if mm else "?"] += 1
for k, c in follow.most_common(15):
    print(f"  {c:4}  {k!r}")
