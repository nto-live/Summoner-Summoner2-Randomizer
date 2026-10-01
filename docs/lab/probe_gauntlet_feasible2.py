"""Boss GAUNTLET feasibility v2 - using the CORRECT level identity (VPP member name).

The boss->level map is recovered via VppFile (member filename -> strip _script.tbl/.tbl, strip
_vN). Doors also belong to members; map each door to its source level the SAME way. Then for each
ordered chain check link-by-link whether a legal door exists in level L to point at level M:
  - name field wide enough: len(M) <= len(door's current dest name)
  - +Index arrival slot provided by M (_level_start_slots)
  - no-+Script door must target a +Script-safe level (_no_script_safe_targets)
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

# blob-offset -> member index
cum = []
acc = 0
for e in vpp.entries:
    cum.append(acc)
    acc += e.size
starts = cum


def member_name(off):
    i = bisect.bisect_right(starts, off) - 1
    return vpp.entries[i].name if 0 <= i < len(vpp.entries) else "?"


def level_from_member(member: str) -> str:
    n = member
    for suf in ("_script.tbl", ".tbl"):
        if n.lower().endswith(suf):
            n = n[: -len(suf)]
            break
    n = re.sub(r"_v\d+$", "", n)
    return n


# boss levels (ordered by first appearance in the stream = roughly progression order)
boss_level_order = []
for s, e in rc._placement_records(blob):
    if b"+Boss" not in blob[s:e]:
        continue
    lv = level_from_member(member_name(s))
    if lv not in boss_level_order:
        boss_level_order.append(lv)
print("boss levels in stream order:", boss_level_order)

# doors: map each to source level via member name
recs = rc._door_records(blob)
slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
kl = {n.lower(): n for n in rc.DOOR_TARGET_NAMES}

doors_by_level = {}
for r in recs:
    lv = level_from_member(member_name(r["off"]))
    doors_by_level.setdefault(lv.lower(), []).append(r)

print("\n=== doors present in each boss level ===")
for lv in boss_level_order:
    ds = doors_by_level.get(lv.lower(), [])
    print(f"  {lv:18} {len(ds)} door(s): " +
          ", ".join(f"{d['name'].decode('latin-1')}(i={d['index']},s={int(d['has_script'])})"
                    for d in ds[:5]))


def legal_link(from_lv, to_lv):
    to_slots = slots.get(rc._door_key(to_lv), set())
    for d in doors_by_level.get(from_lv.lower(), []):
        dn = d["name"].decode("latin-1")
        if len(to_lv) > len(dn):
            continue
        if d["index"] is not None and d["index"] not in to_slots:
            continue
        if not d["has_script"] and rc._door_key(to_lv) not in safe:
            continue
        return d
    return None


print("\n=== can each boss level reach the NEXT one in order? (the gauntlet chain) ===")
chain_ok = 0
for i in range(len(boss_level_order) - 1):
    a, b = boss_level_order[i], boss_level_order[i + 1]
    d = legal_link(a, b)
    print(f"  {a:18} -> {b:18} : " +
          (f"OK via door '{d['name'].decode('latin-1')}' (idx={d['index']})" if d else "NO legal door"))
    chain_ok += bool(d)
print(f"\nordered chain links legal: {chain_ok}/{len(boss_level_order)-1}")

print("\n=== full reachability matrix (how many of the other 10 each can reach) ===")
for a in boss_level_order:
    outs = [b for b in boss_level_order if b != a and legal_link(a, b)]
    print(f"  {a:18} reaches {len(outs)}: {outs}")
