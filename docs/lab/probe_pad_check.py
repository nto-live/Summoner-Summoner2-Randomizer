"""Does $Character tolerate trailing-space padding inside the quotes? The masad freeze (TLB miss
reading 'char'/'model' text as a pointer) suggests my space-padded $Character rename corrupts the
record. enemies_random swaps only EQUAL-length names (no pad). Check: are there ANY $Character
values with trailing spaces in the retail data? If none, padding is illegal and the swap must be
equal-length only. Also: is 'Orenian Scout ' (padded) ever a valid creature? Read-only.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
import rando_core as rc
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)

# any $Character with a trailing space inside the quotes?
padded = list(re.finditer(rb'\$Character\s*:\s*"[^"]*\s"', blob))
print(f"$Character values with trailing space inside quotes: {len(padded)}")
for m in padded[:5]:
    print("  ", m.group(0).decode('latin-1','replace'))

# distribution: how many DISTINCT $Character names, and do equal-length classes exist for a swap?
names = Counter = {}
import collections
c = collections.Counter(m.group(1).decode('latin-1') for m in re.finditer(rb'\$Character\s*:\s*"([^"]+)"', blob))
print(f"\ndistinct $Character names: {len(c)}")
# hostile creature names available at EXACT widths (for equal-length swap)
teams = {}
for m in re.finditer(rb'#Character Info', blob):
    seg = blob[m.start():m.start()+400]
    cm = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    tm = re.search(rb'\$Team\s*:\s*"([^"]+)"', seg)
    if cm and tm:
        teams[cm.group(1).decode('latin-1')] = tm.group(1).decode('latin-1')
hostile = [n for n,t_ in teams.items() if t_ in ('hostile','evil')]
print(f"hostile creature defs: {len(hostile)}")
byw = {}
for n in hostile:
    byw.setdefault(len(n), []).append(n)
print("hostile names by width (for equal-length swap):")
for w in sorted(byw):
    print(f"  w={w:2}: {byw[w]}")
