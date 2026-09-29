"""Scan live EE RAM (via PINE) for movie/stream filename strings, to find what the
boot intro actually loads - independent of any static guess about the player function."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pine import Pine  # noqa: E402

PATS = [b".pss", b".PSS", b".ipu", b".IPU", b"thqlogo", b"demo", b"geeks",
        b"movie", b"MOVIE", b"intro", b"INTRO", b"logo", b"LOGO", b".str", b".STR"]

START = 0x00100000
END = 0x02000000
BLK = 0x100000


def main():
    hits = {}
    with Pine(timeout=30.0) as p:
        addr = START
        while addr < END:
            try:
                buf = p.read_buffer(addr, BLK)
            except Exception as e:  # noqa: BLE001
                print(f"  read fail 0x{addr:08X}: {e}")
                buf = b""
            for pat in PATS:
                i = buf.find(pat)
                while i >= 0 and hits.get(pat, 0) < 8:
                    ea = addr + i
                    ctx = buf[max(0, i - 10):i + 26]
                    hits[pat] = hits.get(pat, 0) + 1
                    print(f"0x{ea:08X} {pat.decode('latin-1'):<8} ctx={ctx!r}", flush=True)
                    i = buf.find(pat, i + 1)
            addr += BLK
    print("done")


if __name__ == "__main__":
    main()
