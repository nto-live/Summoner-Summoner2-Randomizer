"""Find the per-creature XP-on-kill reward field, so we can randomize XP per mob (distinct
from the global xp_scale/xp_boost multipliers)."""
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    print("=== field tokens mentioning xp/exp/reward/experience/kill/bounty ===")
    fields = Counter(m.group(1).decode("latin-1", "replace")
                     for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,30})\s*:', blob))
    for name, c in sorted(fields.items(), key=lambda kv: -kv[1]):
        if any(k in name.lower() for k in ("xp", "exp", "reward", "experience", "kill",
                                            "bounty", "value", "worth", "gain")):
            print(f"  {c:5}  {name}")

    print("\n=== +AddXP: / $Experience style tokens seen anywhere ===")
    for pat in (rb'\+AddXP:\s*\d+', rb'\$Experience:\s*\d+', rb'\$XP:\s*\d+',
                rb'\+XP:\s*\d+', rb'\$Reward:\s*\d+', rb'\+Reward:\s*\d+',
                rb'\$Kill [A-Za-z ]*:\s*\d+', rb'\$Bounty:\s*\d+'):
        ms = list(re.finditer(pat, blob))
        if ms:
            print(f"  {pat.decode():<24} x{len(ms)}   e.g. {ms[0].group(0).decode('latin-1')}")

    print("\n=== is there an XP-like field INSIDE #Character Info (hostile) blocks? ===")
    blocks = rc._hostile_char_blocks(blob)
    print(f"  hostile #Character Info blocks: {len(blocks)}")
    if blocks:
        s, e = blocks[0]
        seg = blob[s:e]
        # list all $/+ numeric fields in the first hostile block
        for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,30}):\s*([0-9.]+)', seg):
            print("   ", m.group(1).decode("latin-1"), "=", m.group(2).decode("latin-1"))


if __name__ == "__main__":
    main()
