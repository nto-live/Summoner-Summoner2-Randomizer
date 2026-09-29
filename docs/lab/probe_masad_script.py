"""Look inside the masad script chunk for tutorial popups/triggers and how flags gate them:
+Messagebox, +Cutscene, +Set/+Check patterns, and any 'controls'/'combat' hint text."""
import os
import re
import sys
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

    # find the masad script region (near the "masad" level file for comment)
    # scan for tutorial-hint message text in the whole blob first
    print("=== hint/instruction text (controls, press, use the) ===")
    for pat in (rb'"[^"]*[Pp]ress [^"]{0,50}"', rb'"[^"]*[Uu]se the [^"]{0,50}"',
                rb'"[^"]*controls?[^"]{0,40}"', rb'"[^"]*[Cc]hain [Aa]ttack[^"]{0,40}"'):
        for m in list(re.finditer(pat, blob))[:6]:
            print("   0x%X  %s" % (t.base + m.start(), m.group(0).decode("latin-1", "replace")[:90]))

    # how are +Flag values used with verbs? show +Action / +Id near a tutorial flag block
    print("\n=== context around the masad flag-declaration block ===")
    m = re.search(rb'masad_basic_controls_tutorial', blob)
    if m:
        s = max(0, m.start() - 400)
        e = min(len(blob), m.start() + 1200)
        chunk = blob[s:e].replace(b"\r", b"")
        print(chunk.decode("latin-1", "replace"))

    # Are these flags checked by a +Condition / +Requires / +If style field?
    print("\n=== verbs that reference flags by value (search a known flag near +) ===")
    for fl in (b"masad_intro", b"masad_spells_tutorial"):
        for m in re.finditer(re.escape(fl), blob):
            s = max(0, m.start() - 25)
            pre = blob[s:m.start()].replace(b"\r", b" ").replace(b"\n", b" ").replace(b"\t", b" ")
            print(f"   ...{pre.decode('latin-1','replace')}[{fl.decode()}]")


if __name__ == "__main__":
    main()
