"""Find how the opening tutorial is represented in TABLES.VPP: tutorial strings,
tutorial-flag fields, hint popups, and what triggers them - so we can disable it safely."""
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

    print("=== 'tutorial' string occurrences (case-insensitive) ===")
    n = 0
    for m in re.finditer(rb"(?i)tutorial", blob):
        s = max(0, m.start() - 40)
        ctx = blob[s:m.end() + 40].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
        print("  0x%X  %s" % (t.base + m.start(), ctx.decode("latin-1", "replace")))
        n += 1
        if n >= 40:
            break
    print(f"  (showing up to 40; more may exist)")

    print("\n=== field tokens mentioning tutorial/hint/tip/help ===")
    fields = Counter(m.group(1).decode("latin-1", "replace")
                     for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,30})\s*:', blob))
    for name, c in sorted(fields.items(), key=lambda kv: -kv[1]):
        if any(k in name.lower() for k in ("tutorial", "hint", "tip", "help", "teach", "lesson", "guide")):
            print(f"  {c:5}  {name}")

    print("\n=== other opening-hint keywords ===")
    for kw in (b"hint", b"Hint", b"HINT", b"press the", b"Press the", b"Use the", b"learn",
               b"training", b"Training", b"controls", b"how to"):
        c = blob.count(kw)
        if c:
            print(f"  {kw.decode():<12} x{c}")


if __name__ == "__main__":
    main()
