"""Sample $Soundtrack vs $Sound values to see music vs sfx."""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)

print("=== $Soundtrack samples (background music) ===")
for m in list(re.finditer(rb'\$Soundtrack:\s*"([^"]+)"', blob))[:12]:
    print("  ", m.group(1).decode("latin-1"))

print("\n=== $Sound samples ===")
for m in list(re.finditer(rb'\$Sound:\s*"([^"]+)"', blob))[:16]:
    print("  ", m.group(1).decode("latin-1"))
