"""Whole-EE-RAM churn scan: which 1MB blocks change over a couple of seconds?

vtlb_ramRead goes through the emulator's own TLB, so this reads exactly what the game sees.
"""
import hashlib
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

BLOCK = 0x40000
START = 0x00100000
END = 0x02000000


def snapshot(p):
    out = {}
    addr = START
    while addr < END:
        try:
            out[addr] = hashlib.md5(p.read_buffer(addr, BLOCK)).hexdigest()[:10]
        except Exception as e:  # noqa: BLE001
            print(f"  0x{addr:08X} read failed: {e}", flush=True)
            out[addr] = "ERR"
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass
            p.__init__(timeout=30.0)
        addr += BLOCK
    return out


def main():
    gap = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    with Pine(timeout=30.0) as p:
        t0 = time.time()
        a = snapshot(p)
        print(f"pass 1 done in {time.time() - t0:.1f}s", flush=True)
        time.sleep(gap)
        b = snapshot(p)
        print(f"pass 2 done in {time.time() - t0:.1f}s", flush=True)
        changed = [k for k in a if a[k] != b[k]]
        print(f"blocks changed: {len(changed)} / {len(a)}")
        for k in changed:
            print(f"  0x{k:08X}  {a[k]} -> {b[k]}")


if __name__ == "__main__":
    main()
