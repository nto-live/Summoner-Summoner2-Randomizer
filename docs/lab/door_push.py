"""Push the live player through a door, with no pad input.

We cannot press buttons, but we CAN write the emulated EE's memory. The door check
(`level_script_check_level_load @ 0x002023C0`) runs every frame and, for a spline trigger,
tests the player's movement segment against the door spline and requires the player to be
inside the door mesh. The player's position lives in the `living_entity` that `Main_entity`
points at (+0x0C = current, +0x18 = previous - they are 12 bytes apart and identical while
standing still), so we can synthesise the movement ourselves.

  python door_push.py probe                       # is the game still running? where is the player?
  python door_push.py push  --axis x --a -60 --b 60
  python door_push.py sweep --seconds 60          # try a set of straddling paths, watch Level_data.name

Stops the moment Level_data.name changes (that is a real level load, caused by the game's own
trigger logic - we only supplied the movement).
"""
import argparse
import struct
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

MAIN_ENTITY = 0x01285980
LEVEL_DATA = 0x01245410
CUR_OFF = 0x0C
PREV_OFF = 0x18

# Door area, read off the live spline nodes next to the trigger's mesh pointer (0x76F5xx):
# y is a constant -5.9; x/z live around 96..111. The player starts at (39.75, -5.22, 88.27).
DOOR = (-5.9, 100.0, 103.0)


def f2i(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def entity(p):
    return p.read(MAIN_ENTITY, 4)


def get_pos(p, e, off):
    return struct.unpack("<3f", p.read_buffer(e + off, 12))


def set_pos(p, e, off, xyz):
    for i, v in enumerate(xyz):
        p.write(e + off + i * 4, 4, f2i(v))


def level_name(p):
    return p.read_string(LEVEL_DATA, 32)


def running(p, addr=0x1200000, length=0x40000, samples=3, gap=0.7):
    import hashlib
    seen = []
    for _ in range(samples):
        seen.append(hashlib.md5(p.read_buffer(addr, length)).hexdigest()[:12])
        time.sleep(gap)
    return seen


def cmd_probe(p):
    e = entity(p)
    print(f"Main_entity = 0x{e:08X}")
    print(f"level       = {level_name(p)!r}")
    print(f"cur  = {get_pos(p, e, CUR_OFF)}")
    print(f"prev = {get_pos(p, e, PREV_OFF)}")
    h = running(p)
    print(f"RAM churn   = {h}  -> {'RUNNING' if len(set(h)) > 1 else 'FROZEN (paused?)'}")


def cmd_push(p, axis, a, b, seconds):
    e = entity(p)
    base = list(DOOR)  # (y, x, z) placeholder, fixed below
    cur0 = get_pos(p, e, CUR_OFF)
    print(f"entity 0x{e:08X}  start {cur0}  level={level_name(p)!r}")
    ax = {"x": 1, "z": 2, "y": 0}[axis]
    A = list(cur0)
    B = list(cur0)
    A[ax] = a
    B[ax] = b
    A[1] = DOOR[0]
    B[1] = DOOR[0]
    print(f"pushing along {axis}: A={tuple(round(v, 2) for v in A)}  B={tuple(round(v, 2) for v in B)}")
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds:
        set_pos(p, e, PREV_OFF, A)
        set_pos(p, e, CUR_OFF, B)
        name = level_name(p)
        if name and name != "masad":
            print(f"*** LEVEL CHANGED -> {name!r} after {n} iterations, {time.time() - t0:.2f}s ***")
            return True
        set_pos(p, e, PREV_OFF, B)
        set_pos(p, e, CUR_OFF, A)
        name = level_name(p)
        n += 2
        if name and name != "masad":
            print(f"*** LEVEL CHANGED -> {name!r} after {n} iterations, {time.time() - t0:.2f}s ***")
            return True
    print(f"no change after {n} writes in {seconds}s")
    return False


def cmd_sweep(p, seconds):
    e = entity(p)
    print(f"entity 0x{e:08X}  level={level_name(p)!r}")
    plans = []
    # straddle the door area from every direction, at a few radii
    for r in (10, 25, 60, 120):
        plans.append(("x", DOOR[1] - r, DOOR[1] + r))
        plans.append(("z", DOOR[2] - r, DOOR[2] + r))
    t0 = time.time()
    for axis, a, b in plans:
        if time.time() - t0 > seconds:
            break
        print(f"--- candidate: {axis}  {a:.1f} -> {b:.1f}")
        if cmd_push(p, axis, a, b, seconds=4.0):
            return True
    print("sweep found nothing")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["probe", "push", "sweep"])
    ap.add_argument("--axis", default="x")
    ap.add_argument("--a", type=float, default=-60)
    ap.add_argument("--b", type=float, default=60)
    ap.add_argument("--seconds", type=float, default=10)
    a = ap.parse_args()
    with Pine() as p:
        if a.action == "probe":
            cmd_probe(p)
        elif a.action == "push":
            cmd_push(p, a.axis, a.a, a.b, a.seconds)
        else:
            cmd_sweep(p, a.seconds)


if __name__ == "__main__":
    main()
