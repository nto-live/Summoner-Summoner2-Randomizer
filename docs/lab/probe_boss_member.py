"""Decisive boss->level mapping test: which VPP MEMBER FILE contains each boss?

discover.py only reads the VPP header; rando_core.VppFile parses the 527-entry TOC
(name[48]+size at +60, 0x800-aligned). blob() is a TIGHT concatenation of member
slices, so a regex hit at blob-offset X maps to member M by accumulating member
sizes. This probe builds that blob-offset -> member-name index and labels every
+Boss placement with the member file that owns it. Read-only.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)

with open(ISO, "rb") as f:
    vpp = rc.VppFile(f, t.base)
    # Build blob-offset table: member i occupies [cum[i], cum[i]+size)
    cum = []
    acc = 0
    for e in vpp.entries:
        cum.append((acc, e.size, e.name))
        acc += e.size
    blob_total = acc
    blob = vpp.blob()

print(f"VPP base 0x{t.base:X}, {vpp.count} members, blob total {blob_total} bytes")
starts = [c[0] for c in cum]

def member_of(off):
    i = bisect.bisect_right(starts, off) - 1
    if i < 0: return None
    base, size, name = cum[i]
    if off < base + size:
        return i, name, off - base
    return i, name + "(gap?)", off - base

# list members whose names look like level files
print("\n=== sample member names (first 40) ===")
for i,(b,s,n) in enumerate(cum[:40]):
    print(f"  [{i:3}] {n!r:40} size={s}")

# find all boss placements, label by member
print("\n=== each +Boss -> containing VPP member ===")
seen_members = {}
for s, e in rc._placement_records(blob):
    if b"+Boss" not in blob[s:e]:
        continue
    ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', blob[s:e])
    mi = member_of(s)
    cname = ch.group(1).decode() if ch else "?"
    print(f"  {cname:22} @blob 0x{s:X} -> member[{mi[0]}] {mi[1]!r} (+0x{mi[2]:X})")
    seen_members.setdefault(mi[1], []).append(cname)

print("\n=== distinct boss-bearing members ===")
for name, bosses in seen_members.items():
    print(f"  {name!r:40} : {bosses}")
