"""Analyse #Character Info blocks: teams, numeric fields, digit widths - the difficulty dials."""
import collections
import re

BLOB = r"F:\rando\S1\notes\_end_blob.bin"
blob = open(BLOB, "rb").read()

# A definition block: "#Character Info" followed by $Character: "name" ...
defs = []
for m in re.finditer(rb"#Character Info", blob):
    s = m.end()
    nxt = re.search(rb"\n#(?!Character Info)", blob[s:])
    e = s + (nxt.start() if nxt else 3000)
    defs.append((s, e, blob[s:e]))

print(f"#Character Info blocks: {len(defs)}")

teams = collections.Counter()
sizes = collections.Counter()
fields = collections.Counter()
widths = collections.defaultdict(collections.Counter)

NUMERIC = (b"$Max Hit Points", b"$Hit Points", b"$Max ability Points", b"$Ability Points",
           b"$Aggressiveness", b"$Teamwork", b"$Conservation", b"$Attack Radius",
           b"$Field of view range", b"$Detection range", b"$Speedup rate", b"$Slowdown rate",
           b"$Slow turn rate", b"$Fast turn rate", b"$Moving turn rate")

for s, e, t in defs:
    m = re.search(rb'\$Team\s*:\s*"?([^"\r\n]*)', t)
    teams[m.group(1).decode("latin-1").strip() if m else "(none)"] += 1
    m = re.search(rb'\$Size\s*:\s*"?([^"\r\n]*)', t)
    sizes[m.group(1).decode("latin-1").strip() if m else "(none)"] += 1
    for f in NUMERIC:
        m = re.search(re.escape(f) + rb"\s*:?\s*([0-9]+)", t)
        if m:
            fields[f.decode()] += 1
            widths[f.decode()][len(m.group(1))] += 1

print(f"\n$Team values: {dict(teams)}")
print(f"$Size values: {dict(sizes)}")
print("\nnumeric fields and their digit-width distributions:")
for k, v in fields.most_common():
    print(f"  {k:22} {v:5}   widths {dict(sorted(widths[k].items()))}")

# how many of the placements (+Monster in #Objects) reference which character names
place = collections.Counter()
for m in re.finditer(rb"\n[ \t]*\$Character\s*:\s*\"([^\"]+)\"(\s*\n(?:[^\n]*\n){0,4}?[ \t]*\+Monster)", blob):
    place[m.group(1).decode("latin-1")] += 1
print(f"\nmonster placements (character -> count): {len(place)} distinct")
for k, v in place.most_common(25):
    print(f"  {v:5}  {k!r}")
print(f"total placements landed: {sum(place.values())}")

# and the definitions seen for those names
defined = {}
for s, e, t in defs:
    m = re.search(rb'\$Character\s*:\s*"?([^"\r\n]*)', t)
    if m:
        defined[m.group(1).decode("latin-1").strip()] = t
missing = [n for n in place if n not in defined]
print(f"\nplaced monster names with no #Character Info block: {len(missing)}  e.g. {missing[:8]}")
if defined:
    sample = next(iter(defined))
    print(f"sample definition {sample}:")
    print(defined[sample].decode("latin-1")[:800])
