"""How does a +Trigger fire a boss? Each gated boss waits on a named trigger, e.g.
+Trigger: "khosanilab2" "pyrulstart". To ACTIVATE the boss on entry we need to understand:
  1. What declares/defines a trigger (a #Triggers section? a $Trigger record with a volume/area?
     a flag?). Find the DEFINITION of 'pyrulstart'/'luminar_intro'/'salstart' etc.
  2. What FIRES it - is it entered as a volume (player walks in), set by a script, or a flag? Is
     there an 'on enter' / area trigger we could place at the player start?
  3. What is 'go' / 'pass go' - the signal 'wait for go' waits on. Is firing the trigger what
     issues 'go'?
Dump the trigger NAMES used by bosses, then search for their DEFINITIONS and the #Triggers section
format. Read-only.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)

# boss trigger names
boss_trigs = set()
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    for m in re.finditer(rb'\+Trigger:\s*"([^"]+)"\s*"([^"]+)"', seg):
        boss_trigs.add((m.group(1).decode(), m.group(2).decode()))
print("=== boss trigger refs (level, trigger-name) ===")
for lv, tn in sorted(boss_trigs):
    print(f"  {lv:16} {tn}")

# a #Triggers section - show its format
print("\n=== a #Triggers section (first one, 400 bytes) ===")
m = re.search(rb'#Triggers', blob)
if m:
    print(blob[m.start():m.start()+400].decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))

# find the DEFINITION of a few boss trigger names (where the name appears NOT as a +Trigger ref)
print("\n=== where each boss trigger NAME appears (all contexts) ===")
for _lv, tn in sorted(boss_trigs):
    tnb = tn.encode()
    occ = list(re.finditer(re.escape(tnb), blob))
    print(f"\n  {tn!r}: {len(occ)} occurrence(s)")
    for mm in occ[:4]:
        ctx = blob[max(0,mm.start()-40):mm.start()+30]
        print(f"     ...{ctx.decode('latin-1','replace')}...".replace('\r','\\r').replace('\n','\\n'))

# how is a trigger fired? look for 'fire'/'set trigger'/'trigger' action commands and 'go'
print("\n=== trigger-firing action commands (sample) ===")
for pat in (rb'\+Action:\s*"[^"]*trigger[^"]*"', rb'\+Action:\s*"[^"]*go[^"]*"', rb'\$Trigger:[^\r\n]{0,40}'):
    print(f"  -- {pat.decode('latin-1')} --")
    seen=set()
    for mm in re.finditer(pat, blob):
        v=mm.group(0)
        if v in seen: continue
        seen.add(v)
        if len(seen)>8: break
        print("    ", v.decode('latin-1','replace'))
