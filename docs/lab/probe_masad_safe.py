"""Model-safe enemy fill for masad (the START level). Must NOT hang the load, so we can only swap
in a creature whose model masad already loads. Find:
  1. which hostile creatures already appear as +Monster placements IN masad (models guaranteed loaded)
  2. masad's peaceful NPC placements, split into likely STORY (named characters) vs non-story
     (generic 'Village Man', 'Soldier', props) - only overwrite non-story
  3. 'Soldier' / 'Orenian' creature names available at masad width
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

mon, peaceful = rc._analyse_enemies(blob)

print("=== creatures already placed as +Monster in masad (models loaded) ===")
masad_monsters = set()
for r in mon:
    if lvl_at(r['start']) == 'masad':
        masad_monsters.add(r['char'].decode('latin-1'))
for c in sorted(masad_monsters):
    print(f"   {c!r} (len {len(c)})")

print("\n=== masad peaceful (NPC) placements: $Name / $Character / width / has-pacifier ===")
PAC = [b"+Hidden", b'"turn hostile"\t0', b'"wait for go"', b'"show/hide"\t0']
for r in peaceful:
    if lvl_at(r['start']) != 'masad':
        continue
    seg = blob[r['start']:r['end']]
    nm = re.search(rb'\$Name\s*:\s*"([^"]+)"', seg)
    pac = any(x in seg for x in PAC)
    print(f"   name={ (nm.group(1).decode() if nm else '?'):22} char={r['char'].decode():18} "
          f"w={len(r['char']):2} pacified={pac}")

# soldier-ish hostile creature names anywhere (to use as the fill), with $Team
print("\n=== 'Soldier'/'Orenian'/'Barbarian' creature defs + team ===")
for m in re.finditer(rb'#Character Info', blob):
    seg = blob[m.start():m.start()+400]
    cm = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    if not cm: continue
    nm = cm.group(1)
    if any(k in nm for k in (b"Soldier", b"Orenian", b"Barbarian", b"Scout")):
        tm = re.search(rb'\$Team\s*:\s*"([^"]+)"', seg)
        print(f"   {nm.decode():22} team={tm.group(1).decode() if tm else '?'} (len {len(nm)})")
