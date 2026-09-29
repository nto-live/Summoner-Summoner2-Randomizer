"""Investigate forcing a guaranteed drop on every enemy.

Questions:
 1. How many hostile #Character Info blocks have zero +Drop entries (would need one added -
    but adding bytes breaks size-preservation, so that's a hard case)?
 2. What is the +Drop weight range/meaning - is a high weight = guaranteed? Can we max it
    size-preservingly (each weight field padded to its own width)?
 3. Do drops sit inside the hostile block, or in a separate table keyed by creature?
"""
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

DROP_RE = re.compile(rb'\+Drop:\s*"([^"]+)"\s*(-?\d+)')


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    # global +Drop weight distribution
    weights = Counter(int(m.group(2)) for m in DROP_RE.finditer(blob))
    print("total +Drop entries:", sum(weights.values()))
    print("weight distribution (sorted):", dict(sorted(weights.items())))
    widths = Counter(len(m.group(2)) for m in DROP_RE.finditer(blob))
    print("weight field widths:", dict(sorted(widths.items())))

    # per hostile block: how many drops does each have?
    blocks = rc._hostile_char_blocks(blob)
    print(f"\nhostile #Character Info blocks: {len(blocks)}")
    drop_counts = []
    zero_drop_names = []
    NAME_RE = re.compile(rb'\$Name:\s*"([^"]+)"')
    for s, e in blocks:
        seg = blob[s:e]
        n = len(DROP_RE.findall(seg))
        drop_counts.append(n)
        if n == 0:
            nm = NAME_RE.search(seg)
            zero_drop_names.append(nm.group(1).decode("latin-1") if nm else "?")
    dc = Counter(drop_counts)
    print("drops-per-hostile distribution:", dict(sorted(dc.items())))
    print(f"hostiles with ZERO drops: {len(zero_drop_names)}")
    if zero_drop_names:
        print("  e.g.:", zero_drop_names[:20])

    # sample a few full +Drop lines to confirm structure (weight = drop chance %?)
    print("\nsample +Drop lines:")
    for m in list(DROP_RE.finditer(blob))[:10]:
        print(f'   +Drop: "{m.group(1).decode("latin-1")}" {m.group(2).decode()}')


if __name__ == "__main__":
    main()
