"""Classify each boss: LIVE-ON-ARRIVAL vs GATED (needs scripted activation).

Signals per boss record:
  - +Hidden            -> invisible until a trigger unhides it => GATED
  - +Trigger "..." "..."-> an intro/activation trigger must fire => GATED (likely)
  - leading 'wait for go' before any 'turn hostile 1' => blocks until 'go' => GATED
  - 'turn hostile 1' with no +Hidden and no leading wait  => LIVE on arrival

Group by level (via VPP member) so we know which LEVELS are all-live (safe gauntlet stops).
Read-only.
"""
import os
import re
import sys
import bisect
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    vpp = rc.VppFile(f, t.base)
    blob = vpp.blob()
cum = []; acc = 0
for e in vpp.entries:
    cum.append(acc); acc += e.size
def lvl_at(off):
    i = bisect.bisect_right(cum, off) - 1
    n = vpp.entries[i].name if 0 <= i < len(vpp.entries) else "?"
    for suf in ("_script.tbl", ".tbl"):
        if n.lower().endswith(suf):
            n = n[:-len(suf)]; break
    return re.sub(r"_v\d+$", "", n)

def classify(seg):
    if b"+Hidden" in seg:
        return "GATED (+Hidden)"
    if b"+Trigger" in seg:
        return "GATED (+Trigger intro)"
    # position of first 'turn hostile 1' vs first 'wait for go'
    th1 = seg.find(b'"turn hostile"\t1')
    if th1 < 0:
        th1 = (re.search(rb'"turn hostile"\s*1', seg) or type('x',(),{'start':lambda s:-1})()).start() if re.search(rb'"turn hostile"\s*1', seg) else -1
    wfg = seg.find(b'"wait for go"')
    if th1 >= 0 and (wfg < 0 or wfg > th1):
        return "LIVE (hostile, no leading wait)"
    if wfg >= 0 and (th1 < 0 or wfg < th1):
        return "GATED (wait for go before hostile)"
    return "UNKNOWN"

by_level = {}
for s, e in rc._placement_records(blob):
    seg = blob[s:e]
    if b"+Boss" not in seg:
        continue
    ch = re.search(rb'\$Character\s*:\s*"([^"]+)"', seg)
    lv = lvl_at(s)
    by_level.setdefault(lv, []).append((ch.group(1).decode() if ch else "?", classify(seg)))

print("=== boss classification by level ===")
all_live_levels = []
for lv, bs in by_level.items():
    live = all("LIVE" in c for _n, c in bs)
    if live:
        all_live_levels.append(lv)
    print(f"\n  {lv}  {'[ALL LIVE]' if live else '[has gated]'}")
    for name, c in bs:
        print(f"     {name:16} {c}")

print(f"\n=== levels where EVERY boss is live-on-arrival (safe gauntlet stops): {all_live_levels}")
