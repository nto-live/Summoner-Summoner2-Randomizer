"""Understand HOW masad tutorial flags fire: where are they referenced (not just
defined), what triggers/messageboxes/cutscenes are attached, and is there a clean
'already done' lever."""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

FLAGS = [
    b"masad_basic_controls_tutorial",
    b"masad_dialogue_tutorial_part1",
    b"masad_basic_combat_tutorial_part1",
    b"masad_spells_tutorial",
    b"masad_chain_attack_tutorial",
]


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    for fl in FLAGS:
        occ = [m.start() for m in re.finditer(re.escape(fl), blob)]
        print(f"=== {fl.decode()} : {len(occ)} occurrence(s) ===")
        for off in occ:
            s = max(0, off - 60)
            ctx = blob[s:off + len(fl) + 60].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
            print("   0x%X  %s" % (t.base + off, ctx.decode("latin-1", "replace")))
        print()

    # What verbs act on flags? +Set flag / +Check flag / +Clear flag etc.
    print("=== flag-action field tokens ===")
    from collections import Counter
    fields = Counter(m.group(1).decode("latin-1", "replace")
                     for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,30})\s*:', blob))
    for name, c in sorted(fields.items(), key=lambda kv: -kv[1]):
        if "flag" in name.lower():
            print(f"  {c:5}  {name}")

    # Is there a global 'skip tutorial' / 'tutorial off' setting or a difficulty/options flag?
    print("\n=== 'skip'/'disable'/'enable tutorial' style strings ===")
    for kw in (b"skip", b"Skip", b"disable", b"Disable", b"enable tutorial", b"tutorial on",
               b"tutorial off", b"show tutorial", b"tutorials"):
        for m in list(re.finditer(re.escape(kw), blob))[:3]:
            s = max(0, m.start() - 30)
            ctx = blob[s:m.end() + 30].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
            print(f"  {kw.decode():<16} {ctx.decode('latin-1','replace')}")


if __name__ == "__main__":
    main()
