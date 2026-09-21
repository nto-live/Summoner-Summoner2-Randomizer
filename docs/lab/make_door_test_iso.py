"""Build a one-door test disc: rewrite ONE `$Trigger:` destination in TABLES.VPP.

This is the randomizer's headline patch, isolated to a single door, so a headless run can show
the level the game actually loads.

  python make_door_test_iso.py catacombs
"""
import json
import shutil
import sys
from pathlib import Path

SRC = Path(r"F:\rando\S1\iso\Summoner.iso")
OUT = Path(r"F:\rando\S1\out")
TRIGGERS = Path(r"F:\rando\S1\notes\door-triggers.json")


def main():
    new_dest = sys.argv[1] if len(sys.argv) > 1 else "catacombs"
    src_level = sys.argv[2] if len(sys.argv) > 2 else "Masad"
    trigs = json.loads(TRIGGERS.read_text(encoding="utf-8"))
    cand = [t for t in trigs if t["src"].lower() == src_level.lower()]
    if len(cand) != 1:
        print(f"expected exactly one door in {src_level}, found {len(cand)}")
        return 1
    t = cand[0]
    old = t["dest"]
    if len(new_dest) > t["len"]:
        print(f"REFUSED: {new_dest!r} is {len(new_dest)} chars, field is {t['len']}")
        return 2
    off = t["iso_offset"]
    old_bytes = old.encode() + b'"'
    new_bytes = new_dest.encode() + b'"' + b" " * (t["len"] - len(new_dest))
    assert len(old_bytes) == len(new_bytes) == t["len"] + 1

    out_iso = OUT / f"test-door1-{new_dest}.iso"
    print(f"{t['src']} door: {old!r} -> {new_dest!r}  (iso 0x{off:X}, {t['len']}+1 bytes)")
    print(f"copying {SRC.name} -> {out_iso.name} ...")
    shutil.copyfile(SRC, out_iso)
    with open(out_iso, "r+b") as f:
        f.seek(off)
        have = f.read(len(old_bytes))
        if have != old_bytes:
            print(f"REFUSED: expected {old_bytes!r} at 0x{off:X}, found {have!r}")
            return 3
        f.seek(off)          # the read above moved the position - seek before writing
        f.write(new_bytes)
        f.seek(off)
        back = f.read(len(new_bytes))
        if back != new_bytes:
            print("READBACK MISMATCH")
            return 4
    print(f"written + read back OK: {back!r}")
    print(f"same size as source: {out_iso.stat().st_size == SRC.stat().st_size}")
    print(out_iso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
