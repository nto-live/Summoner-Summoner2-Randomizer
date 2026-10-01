"""Reconcile boss placements with real level names + the door records' 'src' scheme.

probe_boss_levels used _rooms_sections (#Navpoints); _door_records uses 'Level file for X' heads.
They disagree (bosses -> '?'). Find out how levels are actually delimited around a boss placement:
dump the markers that precede a few boss placements so we can label boss levels the SAME way the
door records do, which is what the gauntlet needs. Read-only.
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

print("DOOR_LEVEL_RE pattern:", rc.DOOR_LEVEL_RE.pattern)
print("total 'Level file' heads:", len(list(rc.DOOR_LEVEL_RE.finditer(blob))))

# what markers exist? show a sample of each kind of header/comment near the start
print("\n=== first 8 DOOR_LEVEL_RE matches ===")
for m in list(rc.DOOR_LEVEL_RE.finditer(blob))[:8]:
    print(f"  @{m.start():#x}: {blob[m.start():m.start()+60]!r}")

# for the first 4 boss placements, dump the 300 bytes before to see what level marker precedes
print("\n=== context before boss placements ===")
n = 0
for s, e in rc._placement_records(blob):
    if b"+Boss" not in blob[s:e]:
        continue
    before = blob[max(0, s-400):s]
    # find any comment-ish or header tokens
    cmts = re.findall(rb'(//[^\r\n]{0,50}|#[A-Za-z][^\r\n]{0,40}|Level[^\r\n]{0,40})', before)
    char = re.search(rb'\$Character\s*:\s*"([^"]+)"', blob[s:e])
    print(f"\n  boss {char.group(1).decode() if char else '?'} @ {s:#x}; preceding markers:")
    for c in cmts[-5:]:
        print(f"     {c.decode('latin-1','replace')!r}")
    n += 1
    if n >= 4:
        break
