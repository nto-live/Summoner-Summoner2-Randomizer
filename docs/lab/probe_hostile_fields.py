import os, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)
blocks = rc._hostile_char_blocks(blob)
fields = Counter()
for s, e in blocks:
    for m in re.finditer(rb'(\$[A-Za-z][A-Za-z0-9 ]{1,28})\s*:', blob[s:e]):
        fields[m.group(1).decode("latin-1")] += 1
print("fields present in hostile #Character Info blocks (name: count):")
for n, c in fields.most_common():
    print(f"  {c:4}  {n}")
