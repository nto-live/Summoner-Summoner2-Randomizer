"""Does a +Drop entry carry a QUANTITY (how many of the item), or only a drop CHANCE?
Request: 'all enemies have drops with 10x items in'. Need to know if 'amount' is editable.
Look at the full +Drop line format and any adjacent quantity/count field."""
import os, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base); blob = f.read(t.total_size)

print("=== raw +Drop lines (full, with surrounding tokens) ===")
for m in list(re.finditer(rb'\+Drop:[^\r\n]{0,60}', blob))[:20]:
    print("  ", m.group(0).decode("latin-1", "replace"))

# is there a +Give / +Quantity / +Amount / +Count near drops?
print("\n=== quantity-ish fields anywhere ===")
fields = Counter(m.group(1).decode("latin-1") for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,28})\s*:', blob))
for fld, c in sorted(fields.items(), key=lambda kv:-kv[1]):
    if any(k in fld.lower() for k in ("give", "amount", "count", "quantity", "qty", "stack", "number", "num ")):
        print(f"  {fld}: {c}")

# +Give context (chests use +Give N; do drops?)
print("\n=== +Give sample (chest/pickup quantity) ===")
for m in list(re.finditer(rb'\+Give:[^\r\n]{0,50}', blob))[:6]:
    print("  ", m.group(0).decode("latin-1","replace"))
