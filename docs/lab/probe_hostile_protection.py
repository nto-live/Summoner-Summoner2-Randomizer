import os, re, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)
blocks = rc._hostile_char_blocks(blob)
print("hostile blocks:", len(blocks))
shown = 0
for s, e in blocks:
    seg = blob[s:e]
    for m in re.finditer(rb'\$Protection[^\r\n]*', seg):
        print("  ", m.group(0).decode("latin-1")); shown += 1
    if shown > 12:
        break
plain = sum(len(re.findall(rb'\$Protection\s*:\s*\d+', blob[s:e])) for s, e in blocks)
flt = sum(len(re.findall(rb'\$Protection\s*:\s*\d+\.\d+', blob[s:e])) for s, e in blocks)
anyp = sum(len(re.findall(rb'\$Protection', blob[s:e])) for s, e in blocks)
print(f"plain-int: {plain}  float: {flt}  any: {anyp}")
