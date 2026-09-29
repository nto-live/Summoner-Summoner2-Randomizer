"""Find the first-level 'firewall' obstacle and what flag gates it dropping, so we can make it
always-down without the blunt skip_tutorial side effect.

The user hit this in the FIRST PLAYABLE LEVEL (masad's follow-on, likely 'sewer' or 'lenele1*').
A wall/barrier that 'drops' is usually an object whose visibility/enable is toggled by a flag
via +Trigger:/+Flag: or a scripted event. Search for firewall/fire-wall/barrier/forcefield
objects and the flags near them."""
import os, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)

print("=== firewall / barrier / forcefield style strings ===")
for kw in (b"firewall", b"Firewall", b"FireWall", b"fire wall", b"fire_wall", b"forcefield",
           b"force field", b"barrier", b"Barrier", b"fire-wall", b"FireBarrier", b"fire barrier",
           b"wall_of_fire", b"WallOfFire", b"flamewall", b"FlameWall"):
    for m in list(re.finditer(re.escape(kw), blob))[:4]:
        s = max(0, m.start()-50); ctx = blob[s:m.end()+60].replace(b"\r",b"").replace(b"\t",b" ").replace(b"\n",b" | ")
        print(f"  {kw.decode():<12} 0x{t.base+m.start():X}  {ctx.decode('latin-1','replace')}")

print("\n=== flags mentioning fire/wall/barrier/tutorial-completion in level flag lists ===")
for m in re.finditer(rb'\+Flag:\s*"([^"]+)"', blob):
    n = m.group(1).decode("latin-1").lower()
    if any(k in n for k in ("fire", "wall", "barrier", "gate", "unlock", "drop", "open")):
        print("  +Flag:", m.group(1).decode("latin-1"))
