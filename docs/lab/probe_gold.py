"""How does a soldier enemy carry/drop GOLD? Need this before adding a 'soldiers drop ~1000 gold'
option. Candidates: +Drop: "Gold" <chance>, +Give: N on a record, a $Gold / $Money creature field,
or a 'Gold' item with an amount somewhere. Find where 'Gold' appears near soldier records and what
numeric field (if any) controls the amount. Read-only.
"""
import os
import re
import sys
from collections import Counter
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

# 1. every way 'Gold' appears as a token, with surrounding field context
print("=== 'Gold' occurrences (sample contexts) ===")
hits = list(re.finditer(rb'Gold', blob))
print(f"  total 'Gold' tokens: {len(hits)}")
ctxs = Counter()
for m in hits:
    seg = blob[max(0, m.start()-24):m.start()+20]
    ctxs[seg] += 1
for seg, c in ctxs.most_common(20):
    print(f"   x{c:4} ...{seg.decode('latin-1','replace')}...".replace("\r","\\r").replace("\n","\\n"))

# 2. soldier / guard creature records and what fields they carry
print("\n=== soldier/guard records: nearby +Drop / +Give / $Gold etc ===")
for name in (b"Soldier", b"Guard", b"soldier", b"guard"):
    for m in list(re.finditer(re.escape(name), blob))[:3]:
        seg = blob[m.start():m.start()+260]
        fields = re.findall(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,20}\s*:[^\r\n]{0,24})', seg)
        print(f"\n  {name.decode()} @ {m.start():#x}:")
        for fld in fields[:10]:
            print(f"     {fld.decode('latin-1','replace')}")

# 3. +Give fields: what values, and are they attached to gold?
print("\n=== +Give lines (sample) ===")
for m in list(re.finditer(rb'\+Give:[^\r\n]{0,40}', blob))[:14]:
    print("  ", m.group(0).decode('latin-1','replace'))

# 4. +Drop "Gold" specifically
print("\n=== +Drop lines mentioning Gold ===")
for m in list(re.finditer(rb'\+Drop:[^\r\n]{0,40}', blob)):
    if b"Gold" in m.group(0):
        print("  ", m.group(0).decode('latin-1','replace'))
