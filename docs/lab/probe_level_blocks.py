"""The stream is organized as 35 #Level blocks; bosses sit in #Objects inside them, and there are
exactly 11 #Boss Info sections (== 11 boss levels). Find the level NAME each #Level block carries,
map each boss to its enclosing #Level, and show the #Boss Info contents. This is the boss->level
key. Read-only.
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

# show a #Level header's bytes to learn how the level name is stored
lvl = [m.start() for m in re.finditer(rb'(?:^|\r\n)#Level\b', blob)]
print(f"{len(lvl)} #Level blocks. First 3 headers (120 bytes each):")
for off in lvl[:3]:
    print(f"  @{off:#x}: {blob[off:off+120]!r}")

# show a #Boss Info block
binfo = [m.start() for m in re.finditer(rb'(?:^|\r\n)#Boss Info\b', blob)]
print(f"\n{len(binfo)} #Boss Info blocks. First 2 (200 bytes each):")
for off in binfo[:2]:
    print(f"  @{off:#x}: {blob[off:off+200]!r}")

# map each #Level block to a name: scan forward from the #Level header for the first plausible
# name token ($Name / "name" / Level file for)
def level_name(off):
    seg = blob[off:off+400]
    for pat in (rb'\$Name\s*:\s*"([^"]+)"', rb'Level file for ([^\r\n*]+)', rb'"([A-Za-z0-9_]{3,24})"'):
        m = re.search(pat, seg)
        if m:
            return m.group(1).decode('latin-1').strip()
    return "?"

lvl_named = [(off, level_name(off)) for off in lvl]
lvl_pos = [o for o, _ in lvl_named]

# bosses -> enclosing #Level
print("\n=== boss -> enclosing #Level name ===")
for s, e in rc._placement_records(blob):
    if b"+Boss" not in blob[s:e]:
        continue
    ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', blob[s:e])
    i = bisect.bisect_right(lvl_pos, s) - 1
    lv = lvl_named[i] if i >= 0 else (0, "?")
    print(f"  {(ch.group(1).decode() if ch else '?'):16} @ {s:#x}  -> #Level @ {lv[0]:#x} = {lv[1]!r}")
