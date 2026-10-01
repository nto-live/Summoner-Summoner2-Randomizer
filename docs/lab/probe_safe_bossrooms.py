"""Model-safe boss rooms: a boss can only be placed in a level that already LOADS its model.
Safest guarantee = place a level's OWN boss creature onto a CLEAN (non-pacified) slot in that SAME
level. So for each boss level, check: does it have clean NPC slots (no +Hidden/turn hostile 0/wait
for go) wide enough to hold its own boss name? Those are the model-safe, aggro-on-arrival rooms.
Then see which can chain, and whether masad (untouched start) can reach the first one.
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

PACIFIERS = [b"+Hidden", b'"turn hostile"\t0', b'"wait for go"', b'"show/hide"\t0']

# bosses per level (their own models are loaded in that level)
boss_names_by_level = {}
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    cm = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    if cm:
        boss_names_by_level.setdefault(lvl_at(s), set()).add(cm.group(1))

# clean peaceful slots per level
mon, peaceful = rc._analyse_enemies(blob)
clean_by_level = {}
for p in peaceful:
    seg = blob[p['start']:p['end']]
    if any(x in seg for x in PACIFIERS):
        continue
    clean_by_level.setdefault(lvl_at(p['start']), []).append(p)

print("=== boss levels: can we place THEIR OWN boss on a clean slot (model-safe, aggro)? ===")
usable = []
for lv, bosses in boss_names_by_level.items():
    clean = clean_by_level.get(lv, [])
    # does a clean slot exist wide enough for at least one of this level's own bosses?
    fits = []
    for p in clean:
        w = len(p['char'])
        ok = [b for b in bosses if len(b) <= w]
        if ok:
            fits.append((p, ok))
    print(f"  {lv:16} own bosses={sorted(x.decode() for x in bosses)}  clean slots={len(clean)}  "
          f"usable(model-safe)={len(fits)}")
    if fits:
        usable.append(lv)

print(f"\nmodel-safe boss-room levels: {usable}")

# chaining among usable + reachable from masad (start, untouched)
slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
recs = rc._door_records(blob)
doors_by_level = {}
for r in recs:
    doors_by_level.setdefault(rc._door_key(lvl_at(r["off"])), []).append(r)
def legal(frm, to):
    for d in doors_by_level.get(rc._door_key(frm), []):
        dn = d["name"].decode("latin-1")
        if len(to) > len(dn): continue
        if d["index"] is not None and d["index"] not in slots.get(rc._door_key(to), set()): continue
        if not d["has_script"] and rc._door_key(to) not in safe: continue
        return d
    return None

print("\n=== masad (start) can legally reach which model-safe boss rooms? ===")
for lv in usable:
    print(f"  masad -> {lv}: " + ("OK" if legal("masad", lv) else "no legal door"))
print("\n=== legal links among model-safe boss rooms ===")
for a in usable:
    outs = [b for b in usable if b != a and legal(a, b)]
    print(f"  {a:16} -> {outs}")
