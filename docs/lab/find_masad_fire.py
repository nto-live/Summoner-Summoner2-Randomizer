"""What is the burning-village fire blocking the player in masad? Find fire objects/effects/
triggers in the masad level and how they're removed (a cutscene, a flag, a scripted event).
This determines if it's tutorial-gated (my patches' fault) or a separate scripted intro event."""
import os, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)

# masad intro/fire cutscene names + fire objects
print("=== masad + fire/burn/intro cutscene & object names ===")
for kw in (b"masad_intro", b"masad_flag_burning", b"burning_man", b"masad_flag_run_away",
           b"Game-Pre-Intro", b"Game-Intro", b"fire", b"Fire", b"burn", b"Burn", b"flame", b"Flame"):
    hits = list(re.finditer(re.escape(kw), blob))
    if hits:
        m = hits[0]; s = max(0, m.start()-40); ctx = blob[s:m.end()+80].replace(b"\r",b"").replace(b"\t",b" ").replace(b"\n",b" | ")
        print(f"  {kw.decode():<20} x{len(hits):<4} e.g. {ctx.decode('latin-1','replace')[:110]}")

# the masad_flag_* set: these are the intro's own progression flags. show the full masad flag block
m = re.search(rb'masad_flag_interrogation', blob)
if m:
    s = max(0, m.start()-40); e = min(len(blob), m.start()+600)
    print("\n=== masad flag block (the intro's progression flags) ===")
    print(blob[s:e].replace(b"\r",b"").decode("latin-1","replace"))
