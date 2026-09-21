"""Look at what the location renderer is handed: FUN_0022b460(0x01278FC8)."""
import struct
import sys

sys.path.insert(0, r"F:\rando\S1\notes")
from dis_va import find_file, ISO  # noqa: E402

VA = 0x01278FC8
name, elf_off, size = find_file(ISO, "SLUS")
fo = elf_off + (VA - 0x00100000) + 0x1000
with open(ISO, "rb") as f:
    f.seek(fo - 32)
    raw = f.read(128)
print(f"{name}: va 0x{VA:08X} -> iso 0x{fo:X}")
print("hex :", raw.hex())
print("text:", raw.decode("latin-1").replace("\x00", "."))
first = struct.unpack("<I", raw[32:36])[0]
print(f"first word at the address: 0x{first:08X}  (pointer? {0x00100000 <= first < 0x02000000})")

print("\n--- and the 32 bytes before it ---")
print("text:", raw[:32].decode("latin-1").replace("\x00", "."))

# also: does the string table for locations exist? dump a wider window as text
with open(ISO, "rb") as f:
    f.seek(fo - 0x200)
    wide = f.read(0x400)
txt = "".join(ch if 32 <= ord(ch) < 127 else ("." if ch == "\x00" else "?") for ch in wide.decode("latin-1"))
print("\n--- 0x200 before .. 0x200 after, printable ---")
print(txt)
