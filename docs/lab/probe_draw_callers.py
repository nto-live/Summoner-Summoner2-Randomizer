"""Are the two draw routines I nopped tutorial-EXCLUSIVE, or shared with combat/HUD?

I nopped the CALL SITES inside ngps_render_tutorial, not the functions themselves, so nop-ing the
call sites cannot break other callers. BUT the targeting cursor vanished on first use, which hints
ngps_render_tutorial (or its neighbours) is entangled with combat UI. Two questions:

  Q1: how many places in the ELF call 0x0022b158 (box) and 0x00133608 (text line)?
      -> tells whether those are general UI primitives (many callers) or tutorial-only.
  Q2: does ngps_process_tutorial / the tutorial step fns touch the targeting cursor? Scan the
      tutorial code range 0x0023c808..0x0023d8f8 for jals and list unique targets, so we can see
      if the tutorial machine calls a cursor/targeting routine at all.

Scan the whole loadable segment for `jal <target>` words. Read-only.
"""
import os
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
loc = binary.find_elf(ISO)

# read the whole loadable segment into memory
with ISO.open("rb") as fh:
    fh.seek(loc.iso_offset + loc.seg_offset)
    seg = fh.read(loc.seg_filesz)
base = loc.seg_vaddr


def jal_target(word):
    if (word >> 26) == 0x03:  # jal
        return (word & 0x03FFFFFF) << 2
    return None


# Q1: count callers of the two draw targets across the whole segment
targets = {0x0022b158: "box draw", 0x00133608: "text-line draw",
           0x00133af0: "text measure", 0x00267418: "line build",
           0x001333c0: "context query", 0x0013bf60: "colour set"}
callers = {t: [] for t in targets}
for i in range(0, len(seg) - 3, 4):
    w = struct.unpack_from("<I", seg, i)[0]
    tgt = jal_target(w)
    if tgt in callers:
        callers[tgt].append(base + i)

print("=== callers of each routine (whole ELF) ===")
for t, name in targets.items():
    cs = callers[t]
    print(f"  0x{t:08X} {name:14}: {len(cs)} caller(s)")
    for c in cs[:12]:
        tut = " [inside tutorial code]" if 0x0023c808 <= c <= 0x0023d8f8 else ""
        print(f"       called from 0x{c:08X}{tut}")

# Q2: all unique jal targets from within the tutorial code region
print("\n=== unique jal targets called from tutorial code 0x0023c808..0x0023d8f8 ===")
lo, hi = 0x0023c808 - base, 0x0023d8f8 - base
tut_targets = Counter()
for i in range(lo, hi, 4):
    w = struct.unpack_from("<I", seg, i)[0]
    tgt = jal_target(w)
    if tgt is not None:
        tut_targets[tgt] += 1
for tgt, c in sorted(tut_targets.items()):
    note = targets.get(tgt, "")
    print(f"  0x{tgt:08X}  x{c}  {note}")
