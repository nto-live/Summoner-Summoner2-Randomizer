"""Find the actual tutorial PROSE anywhere on the disc.

+Messagebox was examine-text, not tutorials. The tutorial help strings must live somewhere; find
them by their words. Scan the WHOLE image for phrases a controls/combat tutorial uses, and report
which region (which VPP, or the ELF) each hit falls in, plus context. Read-only.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
data = ISO.read_bytes()
print(f"image: {len(data):,} bytes")
print("VPPs:")
for v in info.vpps:
    print(f"  base={v.base:#012x} v{v.version} count={v.count} size={v.total_size:,} "
          f"end={v.base + v.total_size:#012x}")


def region(pos):
    for v in info.vpps:
        if v.base <= pos < v.base + v.total_size:
            return f"VPP@{v.base:#x}(v{v.version})+{pos - v.base:#x}"
    return "outside-any-VPP"


phrases = [
    rb"[Ll]eft [Ss]tick", rb"[Rr]ight [Ss]tick", rb"press the", rb"[Pp]ress \x00?.?.?to",
    rb"[Tt]o move", rb"[Dd]-pad", rb"[Aa]nalog", rb"button to", rb"chain attack",
    rb"cast a spell", rb"[Tt]utorial", rb"[Pp]ress .{0,6} to attack", rb"L1", rb"R1",
]
for pat in phrases:
    hits = list(re.finditer(pat, data))
    if not hits:
        continue
    print(f"\n=== {pat!r}: {len(hits)} hit(s) ===")
    for m in hits[:4]:
        ctx = data[max(0, m.start() - 30):m.start() + 80].decode("latin-1", "replace")
        ctx = ctx.replace("\r", "\\r").replace("\n", "\\n").replace("\x00", ".")
        print(f"  @{m.start():#012x} [{region(m.start())}]  ...{ctx}...")
