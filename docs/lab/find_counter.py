"""Look for counter-like values in RAM (proof the game's frame loop is running)."""
import struct
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402


def scan(p, base, length, gap=1.0):
    a = p.read_buffer(base, length)
    time.sleep(gap)
    b = p.read_buffer(base, length)
    diffs = []
    for off in range(0, length - 4, 4):
        x = struct.unpack("<I", a[off:off + 4])[0]
        y = struct.unpack("<I", b[off:off + 4])[0]
        if x != y:
            diffs.append((base + off, x, y))
    print(f"  region 0x{base:08X}+0x{length:X}: {len(diffs)} changed words in {gap}s")
    for addr, x, y in diffs[:25]:
        print(f"    0x{addr:08X}  {x} -> {y}  (d={y - x})")
    return diffs


def main():
    with Pine() as p:
        for base, length in ((0x1200000, 0x80000), (0x200000, 0x80000), (0x800000, 0x80000)):
            scan(p, base, length)


if __name__ == "__main__":
    main()
