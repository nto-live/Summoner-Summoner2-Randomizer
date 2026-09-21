"""Dump a spread of $Character blocks (the enemy spawn/definition records)."""
import re

BLOB = r"F:\rando\S1\notes\_end_blob.bin"
blob = open(BLOB, "rb").read()

pat = re.compile(rb"\n[ \t]*\$Character\s*:")
nxt_pat = re.compile(rb"\n\$[A-Za-z]")
starts = [m.start() for m in pat.finditer(blob)]
print(f"{len(starts)} $Character blocks")

# length distribution
lens = []
for s in starts:
    n = nxt_pat.search(blob, s + 1)
    lens.append((n.start() if n else s + 4096) - s)
lens.sort()
print(f"lengths: min={lens[0]} p25={lens[len(lens)//4]} median={lens[len(lens)//2]} "
      f"p75={lens[3*len(lens)//4]} max={lens[-1]}")

shown = 0
for i in range(0, len(starts), max(1, len(starts) // 20)):
    s = starts[i]
    n = nxt_pat.search(blob, s + 1)
    e = n.start() if n else s + 4096
    t = blob[s:e]
    if len(t) < 120:
        continue
    print(f"\n--- idx {i} @ 0x{s:X}  len {len(t)} ---")
    print(t.decode("latin-1")[:700])
    shown += 1
    if shown >= 10:
        break
