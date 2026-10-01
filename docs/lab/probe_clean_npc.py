"""How many CLEAN NPC slots per level? A swapped-in boss aggros only if the placement it lands on
has no pacifier: no +Hidden, no 'turn hostile 0', no 'wait for go', no 'show/hide 0'. Count clean
peaceful placements (name wide enough for a boss, >=5 chars) per level, so boss_rooms can target
only those. Read-only.
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

PACIFIERS = [b"+Hidden", b'"turn hostile"\t0', b'"turn hostile" 0', b'"wait for go"',
             b'"show/hide"\t0', b'"show/hide" 0']

mon, peaceful = rc._analyse_enemies(blob)
clean_by_level = {}
dirty = 0
for p in peaceful:
    seg = blob[p['start']:p['end']]
    if len(p['char']) < 5:
        continue
    if any(x in seg for x in PACIFIERS):
        dirty += 1
        continue
    clean_by_level.setdefault(lvl_at(p['start']), []).append(p)

print(f"clean (non-pacified, wide) NPC slots by level (dirty skipped: {dirty}):")
for lv, ps in sorted(clean_by_level.items(), key=lambda kv: -len(kv[1]))[:25]:
    print(f"  {lv:18} {len(ps)}")
print(f"\nmasad clean slots: {len(clean_by_level.get('masad', []))}")
# show a couple of clean masad placements
for p in clean_by_level.get('masad', [])[:4]:
    print("   ", repr(blob[p['start']:p['end']][:120]))
