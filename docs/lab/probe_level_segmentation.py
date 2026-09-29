"""Find a reliable marker that segments monster placements by level, so enemies_random can
shuffle WITHIN a level (every creature's model is then already loaded) instead of globally
(which pulled in unloaded models -> missing graphics)."""
import os
import re
import sys
import bisect
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    monsters, _ = rc._analyse_enemies(blob)
    print(f"total monster placements: {len(monsters)}")

    # candidate segmentation markers
    candidates = {
        "Level file for": rb"Level file for ([^\r\n*]{1,40})",
        "#Objects": rb"\n#Objects\b",
        "$Level:": rb'\$Level:\s*"([^"]+)"',
    }
    for label, pat in candidates.items():
        marks = sorted(m.start() for m in re.finditer(pat, blob))
        if not marks:
            print(f"  {label}: no marks"); continue
        # assign each monster to the segment (nearest preceding mark)
        seg_of = {}
        for rec in monsters:
            i = bisect.bisect_right(marks, rec["start"]) - 1
            seg_of[rec["start"]] = i
        counts = Counter(seg_of.values())
        nonempty = [c for c in counts.values() if c]
        print(f"  {label}: {len(marks)} marks, monsters land in {len(counts)} segments, "
              f"median monsters/segment={sorted(nonempty)[len(nonempty)//2] if nonempty else 0}, "
              f"max={max(nonempty) if nonempty else 0}")

    # For the BEST marker (#Objects), show per-segment monster name-length variety - we need
    # >=2 same-length names within a segment for any swap to happen.
    print("\n=== #Objects segmentation: swappable pairs within-level ===")
    marks = sorted(m.start() for m in re.finditer(rb"\n#Objects\b", blob))
    seg_names = {}
    for rec in monsters:
        i = bisect.bisect_right(marks, rec["start"]) - 1
        seg_names.setdefault(i, []).append(rec["char"])
    swappable = 0
    for i, names in seg_names.items():
        byl = Counter(len(n) for n in names)
        swappable += sum(c for c in byl.values() if c >= 2)
    print(f"  placements with >=1 same-length peer in their OWN level: {swappable} / {len(monsters)}")


if __name__ == "__main__":
    main()
