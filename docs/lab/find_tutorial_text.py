"""Find the tutorial popup TEXT records in TABLES.VPP (keyed by/near the masad_*_tutorial flag
names). If the help text is a data record, we may be able to blank it size-preservingly so the
popup is empty/auto-dismissed - a script-layer transform that never touches the flag logic that
gates progression (the firewall)."""
import os, re, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)

# 1) Where do the tutorial flag names appear, and what's around them (text? a record header?)
flags = ["masad_basic_controls_tutorial", "masad_spells_tutorial", "masad_chain_attack_tutorial",
         "masad_skills_tutorial", "masad_basic_combat_tutorial_part1"]
print("=== context around each tutorial flag name occurrence ===")
for fl in flags:
    for m in re.finditer(re.escape(fl).encode(), blob):
        s = max(0, m.start()-30); e = min(len(blob), m.end()+180)
        ctx = blob[s:e].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
        print(f"\n{fl} @0x{t.base+m.start():X}:")
        print("  ", ctx.decode("latin-1", "replace"))

# 2) Look for a #Tutorial / $Tutorial block, or +Tutorial / +Help fields that carry text
print("\n=== tutorial-ish record headers / fields in tables ===")
from collections import Counter
heads = Counter(m.group(1).decode("latin-1") for m in re.finditer(rb'#([A-Za-z][A-Za-z0-9 _]{1,28})', blob))
for h, c in heads.items():
    if "tutor" in h.lower() or "hint" in h.lower() or "help" in h.lower() or "tip" in h.lower():
        print(f"  #{h}: {c}")
fields = Counter(m.group(1).decode("latin-1") for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,28})\s*:', blob))
for fld, c in fields.items():
    if any(k in fld.lower() for k in ("tutor", "hint", "help", "tip", "instruct", "prompt")):
        print(f"  {fld}: {c}")
