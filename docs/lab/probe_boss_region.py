"""What labels the boss region (~0x68000..0x80000)? The bosses sit far BEFORE the first
'Level file for' comment (0x5bb008), so they're in a different part of the stream. Find the
nearest level-identifying token BEFORE each boss: scan back for any 'Level file for', a quoted
level name, a $Script, or a section banner. Read-only."""
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

# collect boss positions
boss_pos = []
for s, e in rc._placement_records(blob):
    if b"+Boss" in blob[s:e]:
        ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', blob[s:e])
        boss_pos.append((s, ch.group(1).decode() if ch else "?"))

print(f"{len(boss_pos)} bosses; first at {boss_pos[0][0]:#x}, last at {boss_pos[-1][0]:#x}")

# any level-name-ish tokens that appear anywhere before 0x90000?
region = blob[:0x90000]
print("\n=== level-ish tokens found in the first 0x90000 bytes ===")
for pat, lbl in [(rb'Level file for ([^\r\n*]+)', 'Level file for'),
                 (rb'Level_info\s*"([^"]+)"', 'Level_info'),
                 (rb'\$Script\s*:\s*"([^"]+)"', '$Script'),
                 (rb'//\s*=+\s*([A-Za-z][A-Za-z0-9 _-]{2,30})', 'banner')]:
    hits = list(re.finditer(pat, region))
    print(f"  {lbl}: {len(hits)} in-region"
          + (f"  e.g. {[h.group(1).decode('latin-1','replace')[:24] for h in hits[:5]]}" if hits else ""))

# for each boss, nearest preceding Level_info or $Script
li = [(m.start(), m.group(1).decode('latin-1','replace')) for m in re.finditer(rb'Level_info\s*"([^"]+)"', blob)]
sc = [(m.start(), m.group(1).decode('latin-1','replace')) for m in re.finditer(rb'\$Script\s*:\s*"([^"]+)"', blob)]
import bisect
li_pos = [x[0] for x in li]; sc_pos = [x[0] for x in sc]
print("\n=== nearest preceding Level_info / $Script for each boss ===")
for s, name in boss_pos:
    i = bisect.bisect_right(li_pos, s) - 1
    j = bisect.bisect_right(sc_pos, s) - 1
    linfo = li[i][1] if i >= 0 else "-"
    scr = sc[j][1] if j >= 0 else "-"
    print(f"  {name:16} @ {s:#x}  Level_info<={linfo!r:24}  $Script<={scr!r}")
