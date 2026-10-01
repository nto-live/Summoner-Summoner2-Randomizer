"""Recover boss -> level mapping. The boss #Objects sections sit at 0x68000..0x386765, but the
first 'Level file for' comment is at 0x5bb008 (AFTER all bosses). So either:
  (A) the stream is: [all #Objects/level-content first] ... [then a block of 'Level file for' door
      definitions], and the two are correlated by ORDER or by a shared level name elsewhere, or
  (B) there's a different section header that opens each level's content block.

Map the big structure: list ALL top-level section headers (#Something) and 'Level file for' heads
in stream order with offsets, and show which headers bracket each boss. Also look for the level
name NEAR each boss by widening the back-scan to any quoted token that also appears as a door
destination / Level_info name. Read-only.
"""
import os
import re
import sys
import bisect
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

# all top-level '#Header' tokens (start of line) and their offsets
headers = [(m.start(), m.group(1).decode('latin-1'))
           for m in re.finditer(rb'(?:^|\r\n)(#[A-Za-z][A-Za-z0-9 _]{0,20})', blob)]
from collections import Counter
hc = Counter(h[1] for h in headers)
print("=== header kinds (count) ===")
for h, c in hc.most_common():
    print(f"  {h:24} {c}")

# the set of known level/door destination names, to recognize a level name when we see one
known = sorted({n for n in rc.DOOR_TARGET_NAMES}, key=len, reverse=True)
known_lc = {n.lower(): n for n in known}

boss_pos = []
for s, e in rc._placement_records(blob):
    if b"+Boss" in blob[s:e]:
        ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', blob[s:e])
        boss_pos.append((s, ch.group(1).decode() if ch else "?"))

# for each boss, scan a WIDE window backward for any known level name appearing as a quoted token
print("\n=== nearest known level-name token before each boss (wide scan) ===")
for s, name in boss_pos:
    lo = max(0, s - 20000)
    window = blob[lo:s]
    best = None
    for m in re.finditer(rb'"([A-Za-z][A-Za-z0-9 _-]{2,30})"', window):
        tok = m.group(1).decode('latin-1')
        if tok.lower() in known_lc:
            best = (tok, s - (lo + m.start()))   # (name, distance back)
    print(f"  {name:16} @ {s:#x}  nearest known-level token: {best}")

# also: what's the FIRST header after offset 0 and the header type that immediately precedes the
# first boss - to understand the level-content container
first_boss = boss_pos[0][0]
pre = [h for h in headers if h[0] < first_boss]
print(f"\nheaders just before first boss ({first_boss:#x}):")
for off, h in pre[-6:]:
    print(f"  @{off:#x}: {h}")
