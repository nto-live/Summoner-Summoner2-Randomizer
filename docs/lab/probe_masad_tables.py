"""Q4 probe: in the TABLES.VPP script stream, examine the masad opening records to
prove the randomizer transforms cannot touch:
  - the masad_dialogue_tutorial_* / masad_basic_* flag NAMES (the +Flag block)
  - the "invis-door01/02/03" object records
  - the door-remap machinery's scope

READ-ONLY. Prints only. Uses rando_core's own VPP reader so it sees exactly the same
bytes the transforms see.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

with ISO.open("rb") as fh:
    bases = rc.find_all_vpps_cached(fh, ISO)
    tb_base, tb = rc.pick_tables(fh, bases)
    print(f"TABLES.VPP base 0x{tb_base:X}, {tb.count} entries")
    blob = tb.blob()

print(f"blob length: {len(blob):,}")


def show_context(needle: bytes, width=90, maxhits=6):
    hits = [m.start() for m in re.finditer(re.escape(needle), blob)]
    print(f'\n--- "{needle.decode(errors="replace")}"  ({len(hits)} occurrence(s)) ---')
    for i, off in enumerate(hits[:maxhits]):
        a = max(0, off - width)
        b = min(len(blob), off + len(needle) + width)
        ctx = blob[a:b].replace(b"\r", b" ").replace(b"\n", b" | ")
        print(f"  @0x{off:X}: ...{ctx.decode('latin-1')}...")
    return hits


# 1. The +Flag block / dialogue flag names in the stream
for nm in (b"masad_dialogue_tutorial_part2a", b"masad_dialogue_tutorial_part2b",
           b"masad_dialogue_tutorial_part3", b"masad_basic_combat_tutorial_part1",
           b"masad_basic_controls_tutorial"):
    show_context(nm, width=60, maxhits=3)

# 2. The invis-door object records
for nm in (b"invis-door01", b"invis-door02", b"invis-door03"):
    show_context(nm, width=70, maxhits=4)

# 3. Is "invis-door02" ever a $Trigger (i.e. in door-remap scope)? and does any door
#    Trigger sit in the masad file?
print("\n" + "=" * 78)
print("Door-remap scope check")
print("=" * 78)
recs = rc.list_doors(blob) if hasattr(rc, "list_doors") else None
# rando_core's door lister may be named differently; try the known private one
door_fn = None
for cand in ("list_doors", "_list_doors", "_doors", "_door_records"):
    if hasattr(rc, cand):
        door_fn = getattr(rc, cand)
        print(f"using rando_core.{cand}()")
        break
if door_fn:
    try:
        recs = door_fn(blob)
        invis_as_door = [r for r in recs if "invis" in str(r.get("name", "")).lower()]
        masad_src = [r for r in recs if "masad" in str(r.get("src", "")).lower()]
        print(f"total doors parsed: {len(recs)}")
        print(f"doors whose NAME contains 'invis': {len(invis_as_door)}")
        for r in invis_as_door:
            print("   ", r)
        print(f"doors whose SOURCE level is masad: {len(masad_src)}")
        for r in masad_src[:20]:
            print("   ", {k: r.get(k) for k in ("src", "name", "id")})
    except Exception as e:  # noqa: BLE001
        print(f"door lister raised: {e!r}")
else:
    print("no door-lister function found on rando_core; listing $Trigger blocks manually")

# manual: every $Trigger whose name contains invis, and its +Id
print("\n$Trigger records mentioning 'invis' (name) anywhere in the stream:")
for m in re.finditer(rb'\$Trigger:\s*"([^"\r\n]{1,40})"', blob):
    if b"invis" in m.group(1).lower():
        tail = blob[m.end():m.end() + 200]
        idm = re.search(rb'\+Id:\s*"([^"]{0,40})"', tail)
        print(f'  @0x{m.start():X} $Trigger:"{m.group(1).decode("latin-1")}"  '
              f'+Id={idm.group(1).decode("latin-1") if idm else "(none within 200B)"}')

# 4. DOOR_SOURCE_EXCLUDE content
print("\nDOOR_SOURCE_EXCLUDE =", rc.DOOR_SOURCE_EXCLUDE)
