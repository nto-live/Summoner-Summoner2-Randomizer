"""Character-definition stats + the remaining spawn knobs."""
import collections
import re

BLOB = r"F:\rando\S1\notes\_end_blob.bin"
blob = open(BLOB, "rb").read()


def show(needle, before=200, after=900, limit=2):
    n = 0
    for m in re.finditer(re.escape(needle.encode()), blob):
        s = max(0, m.start() - before)
        print(f"--- {needle} @ 0x{m.start():X} ---")
        print(blob[s:m.start() + after].decode("latin-1"))
        n += 1
        if n >= limit:
            break


print("=========== a character definition with $Max Hit Points ===========")
show("$Max Hit Points", before=700, after=700, limit=1)

print("\n=========== +Count occurrences ===========")
for m in re.finditer(rb"\+Count", blob):
    s = max(0, m.start() - 150)
    print("---")
    print(blob[s:m.start() + 120].decode("latin-1"))

print("\n=========== value distributions ===========")
for key in ("+Team", "$Class", "$Speed", "$Weight", "$Damage", "$Protection", "$Attack Radius",
            "+Monster", "+Boss", "$Max Hit Points", "+Level"):
    c = collections.Counter()
    for m in re.finditer(re.escape(key.encode()) + rb"\s*:?\s*([^\r\n]*)", blob):
        v = m.group(1).decode("latin-1").strip()[:24]
        c[v] += 1
    print(f"\n{key}  ({sum(c.values())} total, {len(c)} distinct)")
    for k, v in c.most_common(12):
        print(f"   {v:6}  {k!r}")
