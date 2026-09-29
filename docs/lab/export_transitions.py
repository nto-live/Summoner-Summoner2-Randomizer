"""Export every level-change transition (a `#Triggers` block with +Id: "load level") to a
durable JSON map, so future door work reads a validated artifact instead of re-deriving it.

For each door we capture: ISO offset, source level, destination name, +Index (arrival start
id), +Type (spline/location), whether it declares an explicit +Script:, and the field width
head-room. This is the ground truth the remap needs to honour BOTH caveats from
docs/lab/door-mechanism.md 5b:
  1. +Index must exist in the destination (player-start slot), and
  2. a door with NO +Script: uses the destination NAME as its script, so the target must be a
     level whose base script equals its name (the "Exit to Unknown" bug when it doesn't).

We also export each level's provided start-id slots. Nothing here modifies the disc.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(os.path.dirname(os.path.abspath(__file__))) / "transitions.json"

TRIGGER_RE = re.compile(rb'\$Trigger:\s*"([^"\r\n]{1,40})"')
LEVEL_FILE_RE = re.compile(rb"Level file for ([^\r\n*]{1,40})")
BLOCK = 400


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    slots_by_level = rc._level_start_slots(blob)

    heads = [(m.start(), m.group(1).strip().decode("latin-1", "replace"))
             for m in LEVEL_FILE_RE.finditer(blob)]
    doors = []
    src = None
    hi = 0
    for m in TRIGGER_RE.finditer(blob):
        while hi < len(heads) and heads[hi][0] < m.start(1):
            src = heads[hi][1]
            hi += 1
        end = min(m.end() + BLOCK, len(blob))
        nxt = TRIGGER_RE.search(blob, m.end(), end)
        if nxt:
            end = nxt.start()
        seg = blob[m.end():end]
        idm = re.search(rb'\+Id:\s*"([^"]{0,40})"', seg)
        if not idm or idm.group(1) != b"load level":
            continue
        name = m.group(1).decode("latin-1", "replace")
        idx = re.search(rb"\+Index:\s*(\d+)", seg)
        typ = re.search(rb'\+Type:\s*"([^"]+)"', seg)
        scr = re.search(rb'\+Script:\s*"([^"]+)"', seg)
        doors.append({
            "iso_offset": t.base + m.start(1),
            "vpp_offset": m.start(1),
            "src_level": src,
            "dest": name,
            "dest_len": len(name),
            "index": int(idx.group(1)) if idx else None,
            "type": typ.group(1).decode("latin-1") if typ else None,
            "has_script": bool(scr),
            "script": scr.group(1).decode("latin-1") if scr else None,
        })

    export = {
        "iso": ISO.name,
        "tables_base": t.base,
        "tables_bytes": t.total_size,
        "door_count": len(doors),
        "level_start_slots": {k: sorted(v) for k, v in sorted(slots_by_level.items())},
        "doors": doors,
    }
    OUT.write_text(json.dumps(export, indent=2), encoding="utf-8")

    # summary
    from collections import Counter
    print(f"doors: {len(doors)}")
    print("with explicit +Script:", sum(1 for d in doors if d["has_script"]))
    print("no +Script: (name==script constraint):", sum(1 for d in doors if not d["has_script"]))
    print("+Index distribution:", dict(sorted(Counter(d["index"] for d in doors).items(), key=lambda x: (x[0] is None, x[0]))))
    print("+Type distribution:", dict(Counter(d["type"] for d in doors)))
    print("levels with known start slots:", len(slots_by_level))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
