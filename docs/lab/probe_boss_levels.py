"""Which levels contain bosses, and what are their names? Needed to design a boss-gauntlet door
chain (beat area 1's bosses -> exit sends you to area 2's bosses -> ... through all bosses).

For each +Boss placement, find the containing level section and report:
  - the level/section it lives in
  - how many bosses per level
  - the ordered list of boss-bearing levels (candidate gauntlet order)
Read-only.
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

# section starts (reuse the engine's room-section splitter)
sections = rc._rooms_sections(blob)
starts = [s for s, _ in sections]

# try to name each section by the nearest preceding level marker. Levels are introduced by a
# "$Level_info" / level name token; find a reasonable label by scanning back for a quoted name.
def section_label(sec_start):
    window = blob[max(0, sec_start - 4000):sec_start]
    # look for the last Level_info "name" or a $Name-ish level header
    names = re.findall(rb'Level_info\s*"([^"]+)"', window)
    if names:
        return names[-1].decode("latin-1")
    names = re.findall(rb'"([a-z0-9_]{3,20})"', window)
    return names[-1].decode("latin-1") if names else "?"

boss_by_sec = {}
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    m = rc.START_POS_RE.search(seg)
    name = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    sec = bisect.bisect_right(starts, s) - 1
    boss_by_sec.setdefault(sec, []).append(
        (name.group(1).decode("latin-1") if name else "?",
         m.group(2).decode("latin-1") if m else "?"))

print(f"{len(boss_by_sec)} level section(s) contain +Boss placements:\n")
for sec in sorted(boss_by_sec):
    s_start = sections[sec][0]
    print(f"  section #{sec} (~{section_label(s_start)}): {len(boss_by_sec[sec])} boss(es)")
    for char, nav in boss_by_sec[sec]:
        print(f"       {char:28} @ {nav}")

print("\ncandidate gauntlet order (by section index):",
      [sec for sec in sorted(boss_by_sec)])
