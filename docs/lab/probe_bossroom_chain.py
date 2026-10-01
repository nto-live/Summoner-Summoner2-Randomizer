"""Design 'boss rooms': fill a level's NPC placements with hostile boss creatures (size-preserving
$Character rename), then chain level exits. Need levels that (a) have NPC placements with names
wide enough to hold boss names, and (b) can legally door-chain to each other.

For candidate levels, report: # of NPC slots and the max name width (how many bosses fit), plus
their doors. Then find a chain among levels that both qualify. masad is the opening (natural start).
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

BOSS_NAMES = ["Pyrul","Titus","Luminar","Machival","Evil Urath","Ghost Rider","Tiger Rider",
              "Evil Joseph","Phoenix Rider","Serpent Rider","Tentacle Beast","Giant Salamanka"]
minw = min(len(b) for b in BOSS_NAMES)   # 5

# per level: NPC (non-hostile) placement name widths
level_npcs = {}
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Monster" in seg or b"+Boss" in seg:
        continue
    cm = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    if not cm:
        continue
    lv = lvl_at(s)
    level_npcs.setdefault(lv, []).append(len(cm.group(1)))

slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
recs = rc._door_records(blob)
doors_by_level = {}
for r in recs:
    doors_by_level.setdefault(lvl_at(r["off"]).lower(), []).append(r)

def legal(frm, to):
    for d in doors_by_level.get(frm.lower(), []):
        dn = d["name"].decode("latin-1")
        if len(to) > len(dn): continue
        if d["index"] is not None and d["index"] not in slots.get(rc._door_key(to), set()): continue
        if not d["has_script"] and rc._door_key(to) not in safe: continue
        return d
    return None

# levels that can host at least 3 bosses (3+ NPC slots wide enough for the smallest boss name)
hosts = []
for lv, widths in level_npcs.items():
    fits = sum(1 for w in widths if w >= minw)
    if fits >= 3:
        hosts.append((lv, fits, max(widths)))
hosts.sort(key=lambda x: -x[1])
print(f"=== levels that can host >=3 bosses (NPC slots wide enough) : {len(hosts)} ===")
for lv, fits, mx in hosts[:20]:
    nd = len(doors_by_level.get(lv.lower(), []))
    print(f"  {lv:18} fits={fits:2} maxwidth={mx:2} doors={nd}")

# can we chain among host levels? greedy longest path
host_names = [h[0] for h in hosts]
adj = {a: [b for b in host_names if b != a and legal(a, b)] for a in host_names}
best = []
def dfs(node, visited, path):
    global best
    if len(path) > len(best): best = path[:]
    for nxt in adj[node]:
        if nxt not in visited:
            visited.add(nxt); path.append(nxt); dfs(nxt, visited, path); path.pop(); visited.remove(nxt)
for st in host_names:
    dfs(st, {st}, [st])
print(f"\n=== longest chain among host levels: {len(best)} levels ===")
print("  ", " -> ".join(best))
# does the chain start at or near masad (the opening)?
print("\n  masad can host?:", "masad" in host_names, "| masad reaches:", adj.get("masad"))
