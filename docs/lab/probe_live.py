"""Live-memory probes for the Summoner headless test rig.

  python probe_live.py ptr                 # Main_player / Main_entity / Full_party pointers
  python probe_live.py floats <addr> <len> # dump plausible floats (world coords) in a range
  python probe_live.py watch <addr> <off>  # watch 3 floats at addr+off over time
  python probe_live.py find <value>        # find 4-byte little-endian value in the heap window
"""
import struct
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

MAIN_PLAYER = 0x01285978
SUMMON_PLAYER = 0x0128597C
MAIN_ENTITY = 0x01285980
SUMMON_ENTITY = 0x01285984
PLAYER_LIST = 0x0125C080
FULL_PARTY = 0x01284C70
LEVEL_TRIGGERS = 0x1238B78
NUM_TRIGGERS = 0x12844FC


def cmd_ptr(p):
    for name, addr in (("Main_player", MAIN_PLAYER), ("Summon_player", SUMMON_PLAYER),
                       ("Main_entity", MAIN_ENTITY), ("Summon_entity", SUMMON_ENTITY),
                       ("Player_list[0]", PLAYER_LIST), ("Full_party", FULL_PARTY)):
        print(f"{name:16} @0x{addr:08X} = 0x{p.read(addr, 4):08X}")


def cmd_floats(p, addr, length, lo=-100000.0, hi=100000.0):
    raw = p.read_buffer(addr, length)
    for off in range(0, len(raw) - 3, 4):
        (v,) = struct.unpack("<f", raw[off:off + 4])
        if v != v or v == 0.0:
            continue
        if lo < abs(v) < hi and (abs(v) > 0.5):
            i = struct.unpack("<i", raw[off:off + 4])[0]
            print(f"  +0x{off:03X}  0x{i:08X}  f={v:12.4f}")


def cmd_watch(p, addr, off, seconds=30.0, interval=0.5):
    end = time.time() + seconds
    last = None
    while time.time() < end:
        raw = p.read_buffer(addr + off, 12)
        xyz = struct.unpack("<3f", raw)
        s = " ".join(f"{v:10.3f}" for v in xyz)
        if s != last:
            print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)
            last = s
        time.sleep(interval)


def cmd_find(p, value, start=0x00100000, end=0x02000000, chunk=0x100000, maxhits=20):
    needle = struct.pack("<I", value & 0xFFFFFFFF)
    hits = 0
    addr = start
    while addr < end and hits < maxhits:
        raw = p.read_buffer(addr, chunk)
        i = raw.find(needle)
        while i != -1 and hits < maxhits:
            print(f"  hit at 0x{addr + i:08X}  ({addr + i - 0x100000:#x} from RAM start)")
            hits += 1
            i = raw.find(needle, i + 1)
        addr += chunk
    print(f"  {hits} hit(s)")


def main():
    what = sys.argv[1]
    with Pine() as p:
        if what == "ptr":
            cmd_ptr(p)
        elif what == "floats":
            cmd_floats(p, int(sys.argv[2], 0), int(sys.argv[3], 0))
        elif what == "watch":
            cmd_watch(p, int(sys.argv[2], 0), int(sys.argv[3], 0),
                      float(sys.argv[4]) if len(sys.argv) > 4 else 30.0)
        elif what == "find":
            cmd_find(p, int(sys.argv[2], 0))
        else:
            raise SystemExit("unknown action")


if __name__ == "__main__":
    main()
