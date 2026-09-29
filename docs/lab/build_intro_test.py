"""One-off: build a disc that neuters ONLY named opening cutscenes (not all 84),
to test whether skipping just the opening lets the game boot straight to play.

Usage: python build_intro_test.py <out.iso> Name1 [Name2 ...]
Neuters each `$Cutscene: "Name"` by breaking the token to `$Xutscene:` (same single-byte
trick as cutscene_bypass, size-preserving), but only for the named cutscenes.
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import discover  # noqa: E402

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    out = Path(sys.argv[1])
    names = sys.argv[2:]
    if not names:
        print("give at least one cutscene name")
        return 1

    info = discover.identify(str(SRC))
    t = discover.find_tables(info.vpps)

    shutil.copyfile(SRC, out)
    with open(out, "r+b") as f:
        f.seek(t.base)
        blob = bytearray(f.read(t.total_size))
        total = 0
        for name in names:
            pat = re.compile(rb'\$Cutscene:\s*"' + re.escape(name.encode()) + rb'"')
            hits = list(pat.finditer(blob))
            for m in hits:
                # break the 'C' of Cutscene -> 'X'
                i = blob.find(b"Cutscene", m.start())
                blob[i] = ord("X")
                total += 1
            print(f"  {name}: {len(hits)} token(s) neutered")
        f.seek(t.base)
        f.write(blob)
    print(f"total neutered: {total}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
