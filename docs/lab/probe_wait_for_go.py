"""Can a boss be made to activate on arrival? Bosses have +Action: "turn hostile" 0 / "wait for go"
/ "turn hostile" 1. The 'go' is fired elsewhere (a trigger/script). Options to force activation
size-preservingly:
  (A) replace the FIRST '+Action: "turn hostile" 0' with '"turn hostile" 1' (same length) so the
      boss is hostile immediately - does the 0/1 arg control passive-vs-active?
  (B) understand what fires 'go' (a +Trigger volume / a script 'go' command) and whether entering
      the level triggers it.
This probe: show the exact byte layout of the turn-hostile/wait-for-go actions (are '0' and '1'
single chars we can flip?), count how many bosses start with 'turn hostile 0', and find who issues
'go' (search for 'go' action commands and +Trigger records in boss levels). Read-only.
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

# exact bytes of the turn-hostile actions in boss records
print("=== turn hostile / wait-for-go action bytes in boss records ===")
th0 = th1 = wfg = 0
n = 0
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    n += 1
    th0 += len(re.findall(rb'"turn hostile"\s*0', seg))
    th1 += len(re.findall(rb'"turn hostile"\s*1', seg))
    wfg += len(re.findall(rb'"wait for go"', seg))
print(f"{n} boss records: 'turn hostile 0' x{th0}, 'turn hostile 1' x{th1}, 'wait for go' x{wfg}")

# show the raw action list bytes for the first boss with 'turn hostile 0'
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" in seg and b'"turn hostile"\t0' in seg or (b"+Boss" in seg and re.search(rb'"turn hostile"\s*0', seg)):
        m = re.search(rb'"turn hostile"\s*0', seg)
        print("\n=== raw bytes around first 'turn hostile 0' ===")
        print(repr(seg[m.start()-4:m.start()+40]))
        break

# who fires 'go'? search for action command 'go' and 'wait for go' partners, and +Trigger uses
print("\n=== 'go'-ish action commands (sample) ===")
for pat in (rb'"[^"]*\bgo\b[^"]*"', rb'\+Action:\s*"go[^"]*"'):
    hits = list(re.finditer(pat, blob))
    seen = set()
    for m in hits:
        v = m.group(0)
        if v in seen:
            continue
        seen.add(v)
        if len(seen) > 12:
            break
        print("  ", v.decode('latin-1','replace'))

# +Trigger records (what starts a boss intro)
print("\n=== +Trigger records (sample, these may fire 'go') ===")
for m in list(re.finditer(rb'\+Trigger:[^\r\n]{0,50}', blob))[:12]:
    print("  ", m.group(0).decode('latin-1','replace'))
