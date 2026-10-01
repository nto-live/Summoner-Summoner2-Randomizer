"""Can the LIVE-on-arrival boss levels (jadetemple, masad) be door-chained? Only these two have
all-live bosses. Check: does either have a door that can legally point at the other (name width,
+Index slot, +Script-safe)? jadetemple had 0 doors earlier - so likely only masad->jadetemple is
possible, making a 2-stop chain: start -> masad(3 Riders) -> jadetemple(4 Riders, terminal).
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

slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
recs = rc._door_records(blob)
doors_by_level = {}
for r in recs:
    doors_by_level.setdefault(lvl_at(r["off"]).lower(), []).append(r)

live = ["jadetemple", "masad"]
print("=== doors in each live boss level ===")
for lv in live:
    ds = doors_by_level.get(lv.lower(), [])
    print(f"  {lv:12} {len(ds)} door(s): " +
          ", ".join(f"{d['name'].decode('latin-1')}(i={d['index']},s={int(d['has_script'])})" for d in ds))

def legal(frm, to):
    for d in doors_by_level.get(frm.lower(), []):
        dn = d["name"].decode("latin-1")
        if len(to) > len(dn): continue
        if d["index"] is not None and d["index"] not in slots.get(rc._door_key(to), set()): continue
        if not d["has_script"] and rc._door_key(to) not in safe: continue
        return d
    return None

print("\n=== legal links among live levels ===")
for a in live:
    for b in live:
        if a == b: continue
        d = legal(a, b)
        print(f"  {a} -> {b}: " + (f"OK via {d['name'].decode('latin-1')!r} idx={d['index']}" if d else "no legal door"))

# can the START level (masad is the opening!) reach a live level? masad IS a live boss level and
# the opening, so the player naturally starts there. Where can masad legally send the player?
print("\n=== masad is the opening level - where can masad doors legally go (any live target)? ===")
for b in live:
    if b == "masad": continue
    d = legal("masad", b)
    print(f"  masad -> {b}: " + (f"OK via {d['name'].decode('latin-1')!r} idx={d['index']}" if d else "no legal door"))
