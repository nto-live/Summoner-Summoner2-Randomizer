"""Locate the tutorial popup TEXT in TABLES.VPP.

Plan: disable the tutorial popups at the DATA layer (blank the help text) instead of the binary
auto-advance patch, which proved unreliable (fire barrier did not drop). The state machine must
keep running (it sets the flag the firewall depends on); we only want to blank the words shown.

This probe finds:
  1. every `masad_*_tutorial` occurrence and its surrounding bytes (are these +Flag decls, or keys
     into a text record?)
  2. any text-bearing structure near a tutorial key (+NPCText / +Stage / quoted strings / a
     'tutorial' section header)
  3. how 'tutorial' appears as a field/section token anywhere in the blob
Nothing is modified. Read-only recon.
"""
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)
print(f"TABLES stream: {t.total_size:,} bytes\n")


def ctx(pos, before=60, after=90):
    s = max(0, pos - before)
    return blob[s:pos + after].decode("latin-1", "replace").replace("\r", "\\r").replace("\n", "\\n")


# 1. tutorial-named tokens
print("=== distinct tokens containing 'tutorial' (case-insensitive) ===")
toks = Counter(m.group(0).decode("latin-1")
               for m in re.finditer(rb'[A-Za-z_][A-Za-z0-9_ ]*[Tt]utorial[A-Za-z0-9_ ]*', blob))
for tok, c in sorted(toks.items(), key=lambda kv: -kv[1])[:40]:
    print(f"  {c:4}  {tok!r}")

# 2. show context around the first several masad_*_tutorial hits
print("\n=== context around masad_*_tutorial hits (first 12) ===")
for m in list(re.finditer(rb'masad_[A-Za-z0-9_]*tutorial[A-Za-z0-9_]*', blob))[:12]:
    print(f"  @{m.start():#010x}: ...{ctx(m.start())}...")

# 3. section headers / field tokens that mention tutorial (#Tutorial, +Tutorial, $Tutorial...)
print("\n=== structural tokens (#/+/$) near 'tutorial' ===")
for m in list(re.finditer(rb'[#\+\$][A-Za-z][A-Za-z0-9 _]{0,30}', blob)):
    if b"utorial" in m.group(0):
        print(f"  @{m.start():#010x}: {m.group(0).decode('latin-1')!r}  ...{ctx(m.start(), 10, 80)}...")

# 4. is there a '+Help' / '+Text' / '+Message' / '+Tip' style field near tutorial keys?
print("\n=== field tokens appearing anywhere (help/tip/message/text/hint) ===")
fields = Counter(m.group(1).decode("latin-1")
                 for m in re.finditer(rb'([\+\$][A-Za-z][A-Za-z0-9 _]{1,24})\s*[:{]', blob))
for fld, c in sorted(fields.items(), key=lambda kv: -kv[1]):
    if any(k in fld.lower() for k in ("help", "tip", "message", "hint", "tutorial", "text", "popup", "prompt")):
        print(f"  {c:5}  {fld!r}")
