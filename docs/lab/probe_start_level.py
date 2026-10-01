"""How does the game pick the STARTING level? To drop the player straight into a live-boss level
(jadetemple = 4 Riders, or masad = 3 Riders which is the opening), find what sets the initial
level. Candidates: a 'new game' start record, a $Start/$Level entry, a first-door, or a value in
the ELF. Search the script stream for new-game/start markers and the opening level references.
Read-only.
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

# new-game / start-level markers in the script stream
print("=== start/new-game-ish tokens in TABLES stream ===")
for pat in (rb'[^\r\n]{0,30}[Nn]ew [Gg]ame[^\r\n]{0,30}',
            rb'[^\r\n]{0,20}[Ss]tart[ _][Ll]evel[^\r\n]{0,30}',
            rb'\$Start level[^\r\n]{0,30}',
            rb'[^\r\n]{0,20}first level[^\r\n]{0,20}',
            rb'[^\r\n]{0,20}starting[^\r\n]{0,30}'):
    hits = list(re.finditer(pat, blob))
    print(f"\n  {pat[:30]!r}: {len(hits)}")
    for m in hits[:5]:
        print("    ", m.group(0).decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))

# does masad appear as the opening in a config/boot area? find 'masad' refs that aren't level content
print("\n=== 'masad' references with context (first 8) ===")
for m in list(re.finditer(rb'masad', blob))[:8]:
    print("    ", blob[max(0,m.start()-30):m.start()+16].decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))
