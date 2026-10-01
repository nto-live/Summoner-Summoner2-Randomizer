"""Find the LONGEST legal gauntlet path through the boss levels (visit as many as possible, each
once), given the directed legal-link graph. Also report which bosses each visited level contributes,
so we know how many of the 25 bosses the gauntlet covers. Read-only.
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

cum = []
acc = 0
for e in vpp.entries:
    cum.append(acc); acc += e.size
starts = cum
def member_name(off):
    i = bisect.bisect_right(starts, off) - 1
    return vpp.entries[i].name if 0 <= i < len(vpp.entries) else "?"
def level_from_member(member):
    n = member
    for suf in ("_script.tbl", ".tbl"):
        if n.lower().endswith(suf):
            n = n[:-len(suf)]; break
    return re.sub(r"_v\d+$", "", n)

bosses_by_level = {}
order = []
for s, e in rc._placement_records(blob):
    if b"+Boss" not in blob[s:e]:
        continue
    lv = level_from_member(member_name(s))
    ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', blob[s:e])
    bosses_by_level.setdefault(lv, []).append(ch.group(1).decode() if ch else "?")
    if lv not in order:
        order.append(lv)

recs = rc._door_records(blob)
slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
doors_by_level = {}
for r in recs:
    lv = level_from_member(member_name(r["off"])).lower()
    doors_by_level.setdefault(lv, []).append(r)

def legal_link(a, b):
    bs = slots.get(rc._door_key(b), set())
    for d in doors_by_level.get(a.lower(), []):
        dn = d["name"].decode("latin-1")
        if len(b) > len(dn):
            continue
        if d["index"] is not None and d["index"] not in bs:
            continue
        if not d["has_script"] and rc._door_key(b) not in safe:
            continue
        return d
    return None

adj = {a: [b for b in order if b != a and legal_link(a, b)] for a in order}

# longest simple path (brute force; 11 nodes is fine)
best = []
def dfs(node, visited, path):
    global best
    if len(path) > len(best):
        best = path[:]
    for nxt in adj[node]:
        if nxt not in visited:
            visited.add(nxt); path.append(nxt)
            dfs(nxt, visited, path)
            path.pop(); visited.remove(nxt)

for start in order:
    dfs(start, {start}, [start])

covered_bosses = sum(len(bosses_by_level[lv]) for lv in best)
total_bosses = sum(len(v) for v in bosses_by_level.values())
print("longest legal gauntlet path:")
print("  ", " -> ".join(best))
print(f"  visits {len(best)}/{len(order)} boss levels, covering {covered_bosses}/{total_bosses} bosses")
print("\n  bosses along the path:")
for lv in best:
    print(f"    {lv:18} {bosses_by_level[lv]}")
missing = [lv for lv in order if lv not in best]
print(f"\n  boss levels NOT on the path: {missing}")
for lv in missing:
    print(f"    {lv:18} {bosses_by_level[lv]}")
