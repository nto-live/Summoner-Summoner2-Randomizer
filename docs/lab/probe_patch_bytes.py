"""Declare-and-verify the exact current words at every candidate patch address for
the tutorial 'let the player move' question, so any proposed patch states the bytes
it expects and refuses on mismatch. READ-ONLY; prints words + ISO offsets.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
loc = binary.find_elf(ISO)

CANDIDATES = {
    0x0023d74c: "PATCH A: beq s0,zero,0x0023d760  (skip_tutorial v3 NOP target)",
    0x0023d6dc: "cand: beq v0,zero,0x0023d74c  (popup 'waits for input' gate)",
    0x0023d6d8: "context: lw v0,0x4(v0)  (load the +4 waits-for-input field)",
    0x0023d824: "PATCH B word 1: jal 0x0022b158 (popup box draw)",
    0x0023d8c0: "PATCH B word 2: jal 0x00133608 (popup text line)",
    0x0023d5f0: "popup_dismiss/advance entry (lw v0,-0x3a58(gp))",
    0x0023d754: "the gated advance call: jal 0x0023d5f0",
}

with ISO.open("rb") as fh:
    for va, desc in CANDIDATES.items():
        off = binary.va_to_iso_offset(va, loc)
        fh.seek(off)
        w = struct.unpack_from("<I", fh.read(4), 0)[0]
        print(f"{va:#010x}  iso {off:#x}  word=0x{w:08X}   {desc}")
