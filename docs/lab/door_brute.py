"""Brute-force the live door check: synthesise player movement across the door area.

The game is running (Software renderer). `level_script_check_level_load` runs every frame and
tests the player's movement segment against the door spline. We cannot press buttons, but the
player's position fields in the `living_entity` (`Main_entity` +0x0C = current, +0x18 = prev)
are plain memory - so we write them ourselves and let the game's own trigger logic decide.

When Level_data.name (0x01245410) changes, a REAL level load happened, driven by the game.
"""
import argparse
import struct
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

MAIN_ENTITY = 0x01285980
LEVEL_DATA = 0x01245410
LEVEL_DATA_SCRIPT = 0x01245430
LEVEL_DATA_STARTID = 0x012454B4
CUR_OFF = 0x0C
PREV_OFF = 0x18

# Door area read off the live spline nodes next to the trigger mesh (0x76F5xx): y ~ -5.9,
# x ~ 96..111, z ~ 92..112. Player spawns at (39.75, -5.22, 88.27).
DOOR_Y = -5.9


def f2i(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def read_segment(p):
    """The line the door check actually tests against.

    level_script_check_level_load does:  mesh = rec+0x5C ; seg = *(mesh+8) ;
    cross_test(player_prev, player_cur, seg, seg+0xC)  - two 3-float points.
    """
    raw = p.read_buffer(0x1238B78, 100)
    mesh = struct.unpack("<I", raw[0x5C:0x60])[0]
    seg = struct.unpack("<I", p.read_buffer(mesh + 8, 4))[0]
    a = struct.unpack("<3f", p.read_buffer(seg, 12))
    b = struct.unpack("<3f", p.read_buffer(seg + 0xC, 12))
    return mesh, seg, a, b


def normalise(v):
    n = sum(c * c for c in v) ** 0.5
    return tuple(c / n for c in v) if n else (0.0, 0.0, 0.0)


def cross3(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class Rig:
    def __init__(self):
        self.p = Pine()
        self.entity = self.p.read(MAIN_ENTITY, 4)

    def close(self):
        self.p.close()

    def set_pos(self, off, xyz):
        for i, v in enumerate(xyz):
            self.p.write(self.entity + off + i * 4, 4, f2i(v))

    def get_pos(self, off):
        return struct.unpack("<3f", self.p.read_buffer(self.entity + off, 12))

    def level(self):
        return self.p.read_string(LEVEL_DATA, 32)

    def level_info(self):
        return (self.p.read_string(LEVEL_DATA, 32),
                self.p.read_string(LEVEL_DATA_SCRIPT, 32),
                self.p.read(LEVEL_DATA_STARTID, 4))


def attempt(rig, a, b, seconds):
    """Alternate the player between a and b for `seconds`; return the new level name or None."""
    start = rig.level()
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds:
        rig.set_pos(PREV_OFF, a)
        rig.set_pos(CUR_OFF, b)
        n += 1
        name = rig.level()
        if name and name != start:
            return name
        rig.set_pos(PREV_OFF, b)
        rig.set_pos(CUR_OFF, a)
        n += 1
        name = rig.level()
        if name and name != start:
            return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["probe", "push", "grid", "seg"])
    ap.add_argument("--a", default="95,-5.9,100")
    ap.add_argument("--b", default="115,-5.9,100")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--per", type=float, default=1.0)
    a = ap.parse_args()

    rig = Rig()
    print(f"entity 0x{rig.entity:08X}  level={rig.level()!r}  pos={rig.get_pos(CUR_OFF)}")
    if a.action == "probe":
        print(f"prev {rig.get_pos(PREV_OFF)}")
        rig.close()
        return
    if a.action == "seg":
        mesh, seg, A, B = read_segment(rig.p)
        print(f"mesh 0x{mesh:08X}  segment ptr 0x{seg:08X}")
        print(f"  A = {tuple(round(v, 3) for v in A)}")
        print(f"  B = {tuple(round(v, 3) for v in B)}")
        d = tuple(B[i] - A[i] for i in range(3))
        mid = tuple((A[i] + B[i]) / 2 for i in range(3))
        n1 = normalise(cross3(d, (0.0, 1.0, 0.0)))
        n2 = normalise(cross3(d, n1))
        n3 = normalise(d)
        r = None
        trials = []
        for k in (1.0, 2.0, 5.0, 10.0, 25.0, 60.0):
            for n in (n1, n2):
                trials.append((k, n))
                trials.append((k, tuple(-c for c in n)))
        for k, n in trials:
            if r:
                break
            Aa = tuple(mid[i] + k * n[i] for i in range(3))
            Bb = tuple(mid[i] - k * n[i] for i in range(3))
            print(f"  try r={k:5.1f} n={tuple(round(c, 3) for c in n)}  {tuple(round(v, 2) for v in Aa)} <-> {tuple(round(v, 2) for v in Bb)}", flush=True)
            r = attempt(rig, Aa, Bb, 2.0)
        # last resort: travel along the spline direction
        for k in (2.0, 6.0):
            if r:
                break
            Aa = tuple(mid[i] - k * n3[i] for i in range(3))
            Bb = tuple(mid[i] + k * n3[i] for i in range(3))
            print(f"  try along-line k={k}", flush=True)
            r = attempt(rig, Aa, Bb, 2.0)
    elif a.action == "push":
        A = tuple(float(x) for x in a.a.split(","))
        B = tuple(float(x) for x in a.b.split(","))
        print(f"push {A} <-> {B} for {a.seconds}s")
        r = attempt(rig, A, B, a.seconds)
    else:
        r = None
        dirs = [(1, 0, 0), (0, 0, 1), (0.707, 0, 0.707), (0.707, 0, -0.707)]
        for cx in range(94, 116, 4):
            for cz in range(90, 116, 4):
                for d in dirs:
                    A = (cx - 4 * d[0], DOOR_Y, cz - 4 * d[2])
                    B = (cx + 4 * d[0], DOOR_Y, cz + 4 * d[2])
                    print(f"  try centre ({cx}, {DOOR_Y}, {cz}) dir {d}", flush=True)
                    r = attempt(rig, A, B, a.per)
                    if r:
                        break
                if r:
                    break
            if r:
                break
    if r:
        print(f"*** LEVEL LOADED -> {r!r} ***")
        print(f"    Level_data = {rig.level_info()}")
    else:
        print("no level change")
        print(f"    pos now {rig.get_pos(CUR_OFF)} level={rig.level()!r}")
    rig.close()


if __name__ == "__main__":
    main()
