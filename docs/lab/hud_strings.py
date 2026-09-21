"""Read the strings/layout the HUD label renderer draws."""
import struct
import sys

sys.path.insert(0, r"F:\rando\S1\notes")
from dis_va import find_file, ISO  # noqa: E402

name, elf_off, size = find_file(ISO, "SLUS")


def read_va(va, n):
    with open(ISO, "rb") as f:
        f.seek(elf_off + (va - 0x00100000) + 0x1000)
        return f.read(n)


def show(va, n=48, label=""):
    raw = read_va(va, n)
    txt = "".join(ch if 32 <= ord(ch) < 127 else "." for ch in raw.decode("latin-1"))
    print(f"0x{va:08X}  {label}")
    print(f"   text : {txt}")
    print(f"   words: {[hex(w) for w in struct.unpack('<%dI' % (n // 4), raw[:n])]}")


print("=== the fixed label drawn next to the action string ===")
show(0x01285168, 48)
print("\n=== the action string itself ===")
show(0x01278FC8, 32)
print("\n=== the layout table read by the label renderer (8-byte records) ===")
raw = read_va(0x01279608, 64)
for i in range(0, 64, 8):
    a, b = struct.unpack("<2I", raw[i:i + 8])
    print(f"   +0x{i:02X}  {a:#010x} {b:#010x}")
print("\n=== slot index used to pick a record ===")
print("   DAT_00310fd8 lives in .data; value is read live at runtime")
