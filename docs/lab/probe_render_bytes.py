"""Read the real instruction words at ngps_render_tutorial (0x0023d780) and its neighbours,
so a size-preserving early-return patch can DECLARE the exact original bytes it expects.

Also read a few words at ngps_process_tutorial (0x0023d618) for orientation. Read-only.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
loc = binary.find_elf(ISO)
print("ELF:", loc.as_dict())


def words_at(va, n=8):
    off = binary.va_to_iso_offset(va, loc)
    with ISO.open("rb") as fh:
        fh.seek(off)
        raw = fh.read(4 * n)
    return off, [struct.unpack_from("<I", raw, i * 4)[0] for i in range(n)]


def decode_hint(w):
    op = w >> 26
    if w == 0:
        return "nop"
    if w == 0x03E00008:
        return "jr $ra"
    if op == 0x09:
        return f"addiu (imm={w & 0xFFFF:#x})"
    if op == 0x08:
        return f"addi (imm={w & 0xFFFF:#x})"
    if op == 0x0F:
        return f"lui (imm={w & 0xFFFF:#x})"
    if op == 0x23:
        return "lw"
    if op == 0x2B:
        return "sw"
    if op == 0x3F or op == 0x37:
        return "ld/sd-ish"
    if op == 0x04:
        return "beq"
    if op == 0x05:
        return "bne"
    if op == 0x03:
        return "jal"
    if op == 0x02:
        return "j"
    return f"op={op:#x}"


for label, va in (("ngps_render_tutorial", 0x0023d780),
                  ("ngps_process_tutorial", 0x0023d618),
                  ("ngps_init_tutorial", 0x0023d5a8)):
    off, ws = words_at(va, 10)
    print(f"\n{label} @ {va:#010x} (iso {off:#x}):")
    for i, w in enumerate(ws):
        print(f"  {va + i * 4:#010x}: 0x{w:08X}  {decode_hint(w)}")
