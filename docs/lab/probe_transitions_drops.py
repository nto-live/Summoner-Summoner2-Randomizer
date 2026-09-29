"""Survey (1) all transition/trigger +Id: kinds and (2) how enemy drops are stored."""
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    print("=== every +Id: value (count) ===")
    ids = Counter(m.group(1).decode("latin-1", "replace")
                  for m in re.finditer(rb'\+Id:\s*"([^"]{0,40})"', blob))
    for name, n in sorted(ids.items(), key=lambda kv: -kv[1]):
        print(f"  {n:5}  +Id: {name!r}")

    print("\n=== +Type: values inside #Triggers (transition kinds) ===")
    types = Counter(m.group(1).decode("latin-1", "replace")
                    for m in re.finditer(rb'\+Type:\s*"([^"]{0,40})"', blob))
    for name, n in sorted(types.items(), key=lambda kv: -kv[1])[:30]:
        print(f"  {n:5}  +Type: {name!r}")

    print("\n=== drop-related field tokens ===")
    KEYS = ("drop", "give", "loot", "reward", "treasure", "yield", "spawn item",
            "contains", "inventory", "gold", "money", "carr")
    fields = Counter(m.group(1).decode("latin-1", "replace")
                     for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,30})\s*:', blob))
    for name, n in sorted(fields.items(), key=lambda kv: -kv[1]):
        if any(k in name.lower() for k in KEYS):
            print(f"  {n:5}  {name}")

    print("\n=== sample +Give: / drop context (inside a hostile block?) ===")
    for m in list(re.finditer(rb'\+Give:\s*"?([^\r\n"]{0,30})', blob))[:6]:
        s = max(0, m.start() - 120)
        ctx = blob[s:m.end() + 10].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
        print("  ", ctx.decode("latin-1", "replace"))


if __name__ == "__main__":
    main()
