"""Is there a 'bag'/pouch/death-container loot mechanism? The user says 'bag drops'. Search for
bag/pouch/pack/purse/corpse/loot tokens and any +Give/+Drop/+Item attached to them, and the full
structure of a +Drop record (what fields it allows - quantity? gold?). This may be the real
enemy-loot path. Read-only.
"""
import os, re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
with open(ISO,"rb") as f:
    f.seek(t.base); blob=f.read(t.total_size)

for kw in (b"bag", b"Bag", b"pouch", b"Pouch", b"purse", b"corpse", b"loot", b"pack", b"Pack"):
    hits=list(re.finditer(re.escape(kw), blob))
    if hits:
        print(f"=== {kw.decode()}: {len(hits)} ===")
        for m in hits[:6]:
            print("   ", blob[max(0,m.start()-30):m.start()+30].decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))

# full +Drop record structure: show complete +Drop blocks with ALL adjacent + fields
print("\n=== full +Drop context (what fields a drop allows) ===")
for m in list(re.finditer(rb'\+Drop:[^\r\n]*', blob))[:12]:
    s=m.start()
    print("   ", blob[s:s+70].decode('latin-1','replace').replace('\r','\\r').replace('\n','\\n'))

# is 'Gold' ever an ITEM you can drop/give (not just the Messagebox)? and +Give with Gold item
print("\n=== '$Item'/'+Item' lines mentioning Gold or high-value ===")
for m in list(re.finditer(rb'[\$\+]Item:[^\r\n]{0,40}', blob))[:10]:
    print("   ", m.group(0).decode('latin-1','replace'))

# distinct item names that drop (to find 'high level items')
print("\n=== sample distinct dropped item names ===")
items=Counter(m.group(1).decode('latin-1') for m in re.finditer(rb'\+Drop:\s*"([^"]+)"', blob))
for it,c in items.most_common(25):
    print(f"   x{c:3} {it}")
