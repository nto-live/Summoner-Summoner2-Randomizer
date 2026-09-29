"""Count monster placements per #Objects segment (reliable), and show which segments have very
few - to confirm masad (the start area) simply has few enemies by design, not a transform bug."""
import os, re, sys, bisect
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)

monsters, _ = rc._analyse_enemies(blob)
obj = sorted(m.start() for m in re.finditer(rb"\n#Objects\b", blob))
seg_counts = Counter()
for r in monsters:
    seg_counts[bisect.bisect_right(obj, r["start"]) - 1] += 1

# which segment holds masad? masad navpoints look like the level's $player starts. Find the
# segment whose region contains 'masad' asset strings the most.
masad_hits = Counter()
for m in re.finditer(rb"masad", blob):
    masad_hits[bisect.bisect_right(obj, m.start()) - 1] += 1
masad_seg = masad_hits.most_common(1)[0][0] if masad_hits else None
print(f"segment with most 'masad' strings: {masad_seg} -> {seg_counts.get(masad_seg,0)} monster placements")

# distribution: how many segments have <=2 monsters?
low = [s for s, c in seg_counts.items() if c <= 2]
print(f"segments with <=2 monster placements: {len(low)} of {len(seg_counts)}")
print("total segments with any monsters:", len(seg_counts))
print("sample low-count segments (seg: monsters):", {s: seg_counts[s] for s in list(seg_counts)[:15]})
