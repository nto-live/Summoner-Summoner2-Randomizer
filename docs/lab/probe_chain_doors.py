"""Pin down the EXACT door to rewrite for each gauntlet hop, keyed by VPP member (the reliable
identity). For each chain level, list its doors (via member mapping) with the door's current
destination name bytes and the blob offset of that name, plus which target fits. This gives the
transform concrete, declarable edits.

Chain: khosanilab2 -> khosanilab -> rand-hills01 -> IonaExt02 -> sewerboss -> masad -> TempleInt
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

cum = []
acc = 0
for e in vpp.entries:
    cum.append(acc); acc += e.size
starts = cum
def member_name(off):
    i = bisect.bisect_right(starts, off) - 1
    return vpp.entries[i].name if 0 <= i < len(vpp.entries) else "?"
def lvl(member):
    n = member
    for suf in ("_script.tbl", ".tbl"):
        if n.lower().endswith(suf):
            n = n[:-len(suf)]; break
    return re.sub(r"_v\d+$", "", n)

chain = ["khosanilab2", "khosanilab", "rand-hills01", "IonaExt02", "sewerboss", "masad", "TempleInt"]
slots = rc._level_start_slots(blob)
safe = rc._no_script_safe_targets(blob)
recs = rc._door_records(blob)
doors_by_level = {}
for r in recs:
    doors_by_level.setdefault(lvl(member_name(r["off"])).lower(), []).append(r)

def legal(d, target):
    dn = d["name"].decode("latin-1")
    if len(target) > len(dn):
        return False
    if d["index"] is not None and d["index"] not in slots.get(rc._door_key(target), set()):
        return False
    if not d["has_script"] and rc._door_key(target) not in safe:
        return False
    return True

print("=== concrete rewrite per hop ===")
for i in range(len(chain) - 1):
    frm, to = chain[i], chain[i + 1]
    ds = doors_by_level.get(frm.lower(), [])
    chosen = next((d for d in ds if legal(d, to)), None)
    if chosen:
        off = chosen["off"]
        print(f"  {frm} -> {to}: rewrite door at blob 0x{off:X}, "
              f"current dest={chosen['name'].decode('latin-1')!r} (len {len(chosen['name'])}), "
              f"idx={chosen['index']}, has_script={chosen['has_script']}  -> new={to!r} (len {len(to)})")
        # show the raw bytes around the name so the transform can declare-and-refuse
        print(f"      raw: {blob[off-2:off+len(chosen['name'])+2]!r}")
    else:
        print(f"  {frm} -> {to}: NO legal door (unexpected)")
