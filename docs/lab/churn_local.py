"""Local churn scan: uses the pine.py sitting next to this file.

Reads whole EE RAM twice, `gap` seconds apart, and reports how many 1 MB blocks changed.
Frozen VM -> a handful of blocks. Live gameplay -> many. This is how you tell a booted-but-
frozen disc from one that is actually running (see docs/COMPILED-CODE.md §8)."""
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pine import Pine  # noqa: E402

BLOCK = 0x100000        # 1 MB
START = 0x00100000
END = 0x02000000


def snapshot(p):
    out = {}
    addr = START
    while addr < END:
        try:
            out[addr] = hashlib.md5(p.read_buffer(addr, BLOCK)).hexdigest()[:10]
        except Exception as e:  # noqa: BLE001
            out[addr] = f"ERR:{e}"
        addr += BLOCK
    return out


def main():
    gap = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    with Pine(timeout=30.0) as p:
        a = snapshot(p)
        time.sleep(gap)
        b = snapshot(p)
    changed = [k for k in a if a[k] != b[k]]
    print(f"blocks changed: {len(changed)} / {len(a)} over {gap}s")


if __name__ == "__main__":
    main()
