"""Boss GAUNTLET feasibility: can the boss levels' doors be chained A->B->C->...?

For a gauntlet we rewrite ONE door in each boss level to point at the NEXT boss level. For a link
L -> M to be legal (per door_destination_remap's own rules) we need, in level L, a door whose:
  - name field is wide enough to hold M's level name (len(M) <= len(door's current dest name))
  - +Index slot is provided by M (M has a $player*-N navpoint for that index), AND
  - if the door has no +Script, M must be in the +Script-safe set.

This probe:
  1. maps every boss level to its real Level_info name (so we know the node identities),
  2. lists the doors available in each boss level,
  3. for each candidate ordered chain, checks link-by-link whether a legal door exists.
Read-only. Reuses the engine helpers so the rules match the real transform.
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
    f.seek(t.base)
    blob = f.read(t.total_size)

# --- boss levels: map each boss placement's section to the source level name via door records ---
# The door records carry a reliable "src" (the 'Level file for X' comment). Use the same comment
# scheme to label where each boss sits: find the nearest preceding DOOR_LEVEL_RE head.
heads = [(m.start(), m.group(1).strip().decode("latin-1", "replace"))
         for m in rc.DOOR_LEVEL_RE.finditer(blob)]
head_pos = [h[0] for h in heads]


def level_of(pos):
    i = bisect.bisect_right(head_pos, pos) - 1
    return heads[i][1] if i >= 0 else "?"


boss_levels = {}  # level name -> count
for s, e in rc._placement_records(blob):
    if b"+Boss" not in blob[s:e]:
        continue
    lv = level_of(s)
    boss_levels[lv] = boss_levels.get(lv, 0) + 1

print("=== boss levels (by 'Level file for' comment) ===")
for lv, n in boss_levels.items():
    print(f"  {lv:30} {n} boss(es)")

# --- doors available in each boss level ---
recs = rc._door_records(blob)
slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
known = {n.lower() for n in rc.DOOR_TARGET_NAMES}

def door_key(s):
    return rc._door_key(s or "")

doors_by_level = {}
for r in recs:
    doors_by_level.setdefault(door_key(r["src"]), []).append(r)

print("\n=== doors in each boss level ===")
boss_keys = []
for lv in boss_levels:
    k = door_key(lv)
    boss_keys.append((lv, k))
    ds = doors_by_level.get(k, [])
    print(f"  {lv:30} {len(ds)} door(s): "
          + ", ".join(f"{d['name'].decode('latin-1')}(idx={d['index']},scr={int(d['has_script'])})"
                      for d in ds[:6]))


def legal_link(from_level_key, to_level_name):
    """Is there a door in from_level that can legally be rewritten to point at to_level_name?"""
    to_lc = to_level_name.lower()
    to_slots = slots.get(door_key(to_level_name), set())
    for d in doors_by_level.get(from_level_key, []):
        if len(to_level_name) > len(d["name"].decode("latin-1")):
            continue  # name field too narrow
        if d["index"] is not None and d["index"] not in to_slots:
            continue  # destination lacks the arrival slot
        if not d["has_script"] and door_key(to_level_name) not in safe:
            continue  # no-script door must target a script-safe level
        return d
    return None


print("\n=== link feasibility: can boss level L reach boss level M? (any legal door) ===")
names = [lv for lv, _k in boss_keys]
reachable = 0
total = 0
for lv, k in boss_keys:
    outs = []
    for m in names:
        if door_key(m) == k:
            continue
        total += 1
        if legal_link(k, m):
            outs.append(m)
            reachable += 1
    print(f"  {lv:30} -> can legally reach {len(outs)}/{len(names)-1}: {outs[:6]}")

print(f"\nlegal directed links among boss levels: {reachable}/{total}")
print("If most levels can reach most others, a full gauntlet chain is buildable.")
