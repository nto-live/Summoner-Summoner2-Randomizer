"""Confirm the patched TABLES values are resident in the running game's RAM."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pine import Pine  # noqa: E402

START = 0x00100000
END = 0x02000000
BLK = 0x100000


def main():
    dmg99 = 0
    prot = 0
    prot99 = 0
    with Pine(timeout=30.0) as p:
        addr = START
        while addr < END:
            try:
                buf = p.read_buffer(addr, BLK)
            except Exception:  # noqa: BLE001
                buf = b""
            # count weapon damage set to 99 (any whitespace before the number)
            for sep in (b"\t99", b" 99", b"  99"):
                dmg99 += buf.count(b"$Damage:" + sep)
            prot += buf.count(b"$Protection:")
            for sep in (b"\t99", b" 99", b"  99"):
                prot99 += buf.count(b"$Protection:" + sep)
            addr += BLK
    print(f"loaded weapon $Damage:99   occurrences: {dmg99}")
    print(f"loaded $Protection: fields (total): {prot}")
    print(f"loaded $Protection:99      occurrences: {prot99}")


if __name__ == "__main__":
    main()
