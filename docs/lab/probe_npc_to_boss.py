"""Can we replace an NPC placement with a LIVE boss, so the boss fights on arrival?

Compare a boss placement record vs an NPC placement record structurally:
  - A live boss (e.g. a Rider): $Name/$Character + '+Boss' + $Start position + +Action "turn
    hostile" 1 (no wait-for-go, not hidden). Does the HOSTILE BEHAVIOR live in the PLACEMENT
    (+Action list) - which would travel if we rewrite a placement - or in the creature DEFINITION?
  - An NPC placement: $Name/$Character + $Start position, friendly.

Key question for the 'replace NPC with boss' plan: to make a live boss appear where an NPC was, do
we rewrite the NPC's $Character to a hostile creature AND add +Boss/+Action hostile? That changes
record LENGTH (adds +Boss, +Action lines) => NOT size-preserving. OR is just flipping $Character to
a hostile-creature NAME (same width) enough to get a hostile enemy (via enemies_random-style)?

Measure: show a live Rider boss record and a typical temple NPC record side by side with exact
bytes/lengths. List the temple(s) NPC $Character names + widths vs boss names + widths to see what
swaps fit. Read-only.
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
    vpp = rc.VppFile(f, t.base)
    blob = vpp.blob()
cum = []; acc = 0
for e in vpp.entries:
    cum.append(acc); acc += e.size
def lvl_at(off):
    i = bisect.bisect_right(cum, off) - 1
    n = vpp.entries[i].name if 0 <= i < len(vpp.entries) else "?"
    for suf in ("_script.tbl", ".tbl"):
        if n.lower().endswith(suf):
            n = n[:-len(suf)]; break
    return re.sub(r"_v\d+$", "", n)

# a live Rider boss record (full) - what makes it hostile-on-arrival
print("=== a LIVE boss (Ghost Rider in jadetemple) full record ===")
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" in seg and b"Ghost Rider" in seg and lvl_at(s) == "jadetemple":
        print(repr(seg[:300]))
        break

# How is 'hostile' determined? Is it the +Boss/+Action in the placement, or the creature $Team in
# the #Character Info definition? Check the Rider creature definition's $Team.
print("\n=== creature definition $Team for a Rider (hostile?) ===")
for name in (b"Ghost Rider", b"Tiger Rider"):
    for m in re.finditer(rb'#Character Info', blob):
        seg = blob[m.start():m.start()+400]
        if name in seg:
            tm = re.search(rb'\$Team\s*:\s*"([^"]+)"', seg)
            print(f"  {name.decode()}: $Team={tm.group(1).decode() if tm else '?'}")
            break

# temple NPC placements: names + widths, vs boss names + widths
print("\n=== TempleInt / jadetemple NPC placement $Character names (width) ===")
for target in ("TempleInt", "jadetemple", "masad"):
    chars = {}
    for s, e in rc._placement_records(blob):
        if lvl_at(s) != target:
            continue
        seg = blob[s:e]
        if b"+Monster" in seg or b"+Boss" in seg:
            continue  # skip existing hostiles
        cm = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
        if cm:
            nm = cm.group(1).decode('latin-1')
            chars[nm] = len(nm)
    print(f"\n  {target}: {len(chars)} non-hostile placements; sample names+widths:")
    for nm, w in list(chars.items())[:12]:
        print(f"     [{w:2}] {nm!r}")

print("\n=== boss $Character names + widths (what we'd swap IN) ===")
bosses = {}
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    cm = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    if cm:
        bosses[cm.group(1).decode('latin-1')] = len(cm.group(1))
for nm, w in sorted(bosses.items(), key=lambda kv: kv[1]):
    print(f"  [{w:2}] {nm!r}")
