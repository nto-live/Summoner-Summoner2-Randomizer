"""Census of monster ($Character +Monster) blocks: fields, values, and how they are placed."""
import collections
import re

BLOB = r"F:\rando\S1\notes\_end_blob.bin"
blob = open(BLOB, "rb").read()
char_pat = re.compile(rb"\n[ \t]*\$Character\s*:")
nxt_pat = re.compile(rb"\n\$[A-Za-z]")

blocks = []
for m in char_pat.finditer(blob):
    s = m.start()
    n = nxt_pat.search(blob, s + 1)
    e = n.start() if n else min(len(blob), s + 4096)
    blocks.append((s, e, blob[s:e]))

mon = [b for b in blocks if b"+Monster" in b[2]]
print(f"blocks: {len(blocks)}   with +Monster: {len(mon)}")
other = [b for b in blocks if b"+Monster" not in b[2]]
print(f"without +Monster: {len(other)}")

keys = collections.Counter()
for s, e, t in mon:
    for m in re.finditer(rb"\n[ \t]*([+\$][A-Za-z][A-Za-z ]{1,24}):", t):
        keys[m.group(1).decode("latin-1")] += 1
print("\nfields inside +Monster blocks:")
for k, v in keys.most_common(50):
    print(f"  {v:7}  {k}")

lv = collections.Counter()
for s, e, t in mon:
    m = re.search(rb"\+Level\s*:\s*([0-9]+)", t)
    lv[m.group(1).decode() if m else "(none)"] += 1
print("\n+Level values (top 25 of", len(lv), "distinct):")
for k, v in sorted(lv.items(), key=lambda kv: -kv[1])[:25]:
    print(f"  {v:7}  +Level: {k}")

names = collections.Counter()
for s, e, t in mon:
    m = re.search(rb'\$Character\s*:\s*"([^"]*)"', t)
    names[m.group(1).decode("latin-1") if m else "?"] += 1
print(f"\ndistinct monster names: {len(names)}  (top 20)")
for k, v in names.most_common(20):
    print(f"  {v:7}  {k!r}")

# a few long monster blocks, in full
longs = sorted((b for b in mon if len(b[2]) > 150), key=lambda b: -len(b[2]))[:3]
for s, e, t in longs:
    print(f"\n--- monster block @ 0x{s:X}  len {e - s} ---")
    print(t.decode("latin-1")[:1200])
