"""Confirm the exact original words at the two popup-draw jal sites in ngps_render_tutorial,
so hide_tutorials can be rewritten to nop ONLY those two draws (box + text lines) while leaving
the load-bearing 'rendered' flag write and the layout/build calls intact.

  0x0023d824  jal 0x0022b158   (popup panel/box draw)   expect encoded jal to 0x0022b158
  0x0023d8c0  jal 0x00133608   (text-line draw)         expect encoded jal to 0x00133608

jal encoding: (0x03 << 26) | ((target >> 2) & 0x03FFFFFF). Verify the words on disc match.
Read-only.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
loc = binary.find_elf(ISO)


def jal_word(target):
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def read_word(va):
    off = binary.va_to_iso_offset(va, loc)
    with ISO.open("rb") as fh:
        fh.seek(off)
        return off, struct.unpack("<I", fh.read(4))[0]


for va, target, name in ((0x0023d824, 0x0022b158, "box draw"),
                         (0x0023d8c0, 0x00133608, "text-line draw")):
    off, w = read_word(va)
    expect = jal_word(target)
    print(f"{name:14} @ {va:#010x} (iso {off:#x}): on-disc=0x{w:08X}  "
          f"expected jal 0x{target:06X}=0x{expect:08X}  "
          f"{'MATCH' if w == expect else 'MISMATCH'}")
