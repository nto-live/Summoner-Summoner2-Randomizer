"""Spot-check a built ISO: gear buffs, enemy HP, and the binary patches, read back byte-for-byte.
Defaults to the CHAOS disc; pass an ISO path as argv[1] to check another."""
import re
import struct
import sys
from _paths import OUT_DIR
import discover
import binary

ISO = sys.argv[1] if len(sys.argv) > 1 else str(OUT_DIR / "Summoner-CHAOS.iso")

info = discover.identify(ISO)
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)


def sample(label, pat):
    m = re.search(pat, blob, re.S)
    print(f"  {label:<32} -> {m.group(1).decode() if m else '(not found)'}")


print("=== gear buffs ===")
sample("Berserker Sword $Damage", rb"Berserker Sword.{0,220}?\$Damage:\s*(\d+)")
sample("GlassSword $Damage", rb"GlassSword.{0,260}?\$Damage:\s*(\d+)")
sample("leather cap $Protection", rb"leather cap.{0,140}?\$Protection:\s*(\d+)")

print("=== enemy HP (first 12 $Max Hit Points) ===")
print("  ", [m.decode() for m in re.findall(rb"\$Max Hit Points:\s*(\d+)", blob)[:12]])

print("=== binary patches in ISO ===")
loc = binary.find_elf(ISO)
with open(ISO, "rb") as f:
    for va, expect in ((0x002419C0, "skip_intro jr ra"), (0x0023D74C, "skip_tutorial nop")):
        f.seek(binary.va_to_iso_offset(va, loc))
        w = struct.unpack("<I", f.read(4))[0]
        print(f"  0x{va:08X} = 0x{w:08X}  ({expect})")
