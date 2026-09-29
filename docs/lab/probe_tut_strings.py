"""Map the tutorial STRING block and the ngps_render_tutorial symbol.

Two candidate clean fixes (both leave the flag state machine intact):
  A) blank the tutorial help strings in place (data segment ~0x12f39000), size-preserving
  B) early-return ngps_render_tutorial @0x0023d780 (draw-only, per the map file)

This probe: (1) dumps the contiguous tutorial-string block so we know its extent and can bound a
safe blank; (2) pulls the map-file lines around ngps_render_tutorial to see its neighbours and
confirm it is a render (draw) function distinct from the step/flag functions. Read-only.
"""
import re
import sys
from pathlib import Path

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
data = ISO.read_bytes()

# ---- A: the tutorial string block ----
# Anchor on a known line and walk outward over printable/newline runs.
anchor = data.find(b"using the Left Analog Stick")
print(f"anchor 'Left Analog Stick' @ {anchor:#012x}")
lo = anchor
while lo > anchor - 0x4000 and (32 <= data[lo - 1] < 127 or data[lo - 1] in (10, 13, 0, 0xAD, 0xAE, 0xAF)):
    lo -= 1
hi = anchor
while hi < anchor + 0x6000 and (32 <= data[hi] < 127 or data[hi] in (10, 13, 0, 0xAD, 0xAE, 0xAF)):
    hi += 1
block = data[lo:hi]
printable = sum(1 for c in block if 32 <= c < 127 or c in (10, 13))
print(f"string block ~[{lo:#x}..{hi:#x}] len={hi - lo} printable_ratio={printable / len(block):.2f}")
# split into the individual NUL/newline-delimited strings that look like tutorial text
strings = re.split(rb'[\x00]{1,}', block)
kw = (b"stick", b"press", b"button", b"attack", b"spell", b"skill", b"move", b"camera",
      b"target", b"menu", b"summon", b"chain", b"Joseph")
tut = [s for s in strings if len(s) > 20 and any(k in s.lower() for k in kw)]
print(f"\n=== {len(tut)} tutorial-ish strings in the block (first 25) ===")
for s in tut[:25]:
    txt = s.decode("latin-1", "replace").replace("\r", "\\r").replace("\n", "\\n")
    print(f"  [{len(s):3}] {txt[:110]}")

# ---- B: the map file lines around ngps_render_tutorial ----
mp = data.find(b"ngps_render_tutorial(void)")
print(f"\nngps_render_tutorial symbol text @ {mp:#012x}")
if mp > 0:
    seg = data[mp - 200:mp + 600].decode("latin-1", "replace")
    for line in seg.splitlines():
        if "0x00000000002" in line or "tutorial" in line.lower():
            print("  ", line.strip())
