"""What makes a hostile creature actually AGGRO (attack on sight) vs stand idle? For the boss-rooms
swap, a boss creature may spawn but not attack if its placement had a passive +Action, or if its
$Team/aggression/detection stats keep it idle. Examine:
  1. the boss creatures' #Character Info: $Team, $Aggressiveness, $Detection range, $Attack Radius
  2. whether a PLACEMENT's +Action controls initial hostility ('turn hostile' 0 vs 1) and whether a
     plain NPC placement (what we overwrite) has any +Action that would keep the swapped-in boss
     passive.
Compare a normal hostile MONSTER placement (which does aggro) vs an NPC placement, to see what the
monster has that the NPC lacks. Read-only.
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

# 1. boss creature combat stats
print("=== boss creature #Character Info stats ===")
for name in (b"Ghost Rider", b"Luminar", b"Pyrul", b"Giant Salamanka"):
    for m in re.finditer(rb'#Character Info', blob):
        seg = blob[m.start():m.start()+600]
        if re.search(rb'\$Character\s*:\s*"' + re.escape(name) + rb'"', seg):
            team = re.search(rb'\$Team\s*:\s*"([^"]+)"', seg)
            agg = re.search(rb'\$Aggressiveness\s*:\s*(\d+)', seg)
            det = re.search(rb'\$Detection range\s*:\s*([0-9.]+)', seg)
            atk = re.search(rb'\$Attack Radius\s*:\s*([0-9.]+)', seg)
            fov = re.search(rb'\$Field of view range\s*:\s*([0-9.]+)', seg)
            print(f"  {name.decode():16} team={team.group(1).decode() if team else '?':8} "
                  f"aggr={agg.group(1).decode() if agg else '?':4} det={det.group(1).decode() if det else '?':6} "
                  f"atkR={atk.group(1).decode() if atk else '?':5} fov={fov.group(1).decode() if fov else '?'}")
            break

# 2. compare a normal MONSTER placement vs an NPC placement: what +Action / fields differ
print("\n=== a normal +Monster placement (that DOES aggro) ===")
mon, peaceful = rc._analyse_enemies(blob)
import re as _re
m0 = mon[0]
print(repr(blob[m0['start']:m0['end']][:200]))
print("\n=== a peaceful NPC placement (what boss_rooms overwrites) ===")
p0 = peaceful[0]
print(repr(blob[p0['start']:p0['end']][:200]))

# do NPC placements carry +Action that could pacify a swapped-in creature?
print("\n=== +Action usage in peaceful placements (do any force passive?) ===")
from collections import Counter
acts = Counter()
for p in peaceful:
    seg = blob[p['start']:p['end']]
    for mm in re.finditer(rb'\+Action:\s*"([^"]+)"', seg):
        acts[mm.group(1).decode('latin-1')] += 1
for a, c in acts.most_common(15):
    print(f"  x{c:4} {a!r}")
