"""Force the live door trigger to be a *direct* load (clear the 'run script' flag bit) and watch.

level_script_check_level_load takes the load-the-level branch only when
`(flags & 2) == 0`; when bit 1 is set it calls level_script_do_clicked() and runs a scripted
action instead. The retail `masad` door is scripted (flags = 3), so with the geometry gates
forced open it still will not change level. Clearing that bit makes it a plain door.
"""
import struct
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

TRIG = 0x1238B78
NUM_TRIG = 0x12844FC
LEVEL_NAME = 0x1245410
LEVEL_SCRIPT = 0x1245430
LEVEL_STARTID = 0x12454B4


def show(p, tag):
    n = p.read_string(TRIG + 0x00, 32)
    print(f"{tag}: name={n!r} id={p.read(TRIG + 0x48, 4)} type={p.read(TRIG + 0x4C, 4)} "
          f"flags={p.read(TRIG + 0x54, 4)} scriptptr=0x{p.read(TRIG + 0x20, 4):08X} "
          f"startid={p.read(TRIG + 0x50, 4)}")


def main():
    newname = sys.argv[1] if len(sys.argv) > 1 else None
    with Pine(timeout=20.0) as p:
        print(f"triggers = {p.read(NUM_TRIG, 4)}   level = {p.read_string(LEVEL_NAME, 32)!r}")
        show(p, "record before")
        if newname:
            raw = newname.encode()
            assert len(raw) <= 31
            field = raw + b"\x00" + b" " * (31 - len(raw))
            for i in range(0, 32, 4):
                p.write(TRIG + i, 4, struct.unpack("<I", field[i:i + 4])[0])
            print(f"destination rewritten -> {p.read_string(TRIG, 32)!r}")
        p.write(TRIG + 0x54, 4, 1)   # clear the run-script flag -> plain level load
        show(p, "record after ")
        t0 = time.time()
        last = None
        while time.time() - t0 < 40:
            nm = p.read_string(LEVEL_NAME, 32)
            if nm != last:
                print(f"[{time.time() - t0:5.1f}s] Level_data.name = {nm!r} "
                      f"script={p.read_string(LEVEL_SCRIPT, 32)!r} startid={p.read(LEVEL_STARTID, 4)}",
                      flush=True)
                last = nm
            if nm and nm != "masad":
                print(f"*** LEVEL LOADED -> {nm!r} ***")
                break
            time.sleep(0.25)
        else:
            print("no level change in 40s")


if __name__ == "__main__":
    main()
