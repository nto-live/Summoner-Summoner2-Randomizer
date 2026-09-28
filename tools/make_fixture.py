"""Build a local measurement fixture from the user's own disc.

Why this exists: the transform layer edits the reassembled `TABLES.VPP` stream, and almost
every claim in this repo is *measured* - edit counts, size preservation, whole-stream diff
cleanliness. To measure, you need that stream. It is 6.7 MB of raw game data, so it is **not**
in this repo and never will be. This script regenerates it from a disc the user already owns,
so anyone can measure offline without an emulator or an ISO in git.

Usage
-----
    python tools/make_fixture.py --iso "D:\\Summoner.iso" --out work/tables_blob.bin
    python tools/make_fixture.py --check work/tables_blob.bin

`--check` is the part that matters. It proves the fixture is *correct*, not merely present:
a fixture built with the old (wrong) archive-offset rule sees **1** of the 218 doors, because
it is missing the level files. A correct one sees all 218. If you get anything other than 218,
throw the file away and rebuild - do not measure against it.

The output file is game data. Keep it in `work/` (gitignored). Never commit it, never share it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rando_core as rc  # noqa: E402

EXPECTED_DOORS = 218
EXPECTED_BYTES = 6_771_975  # the stream's length is stable across both offset rules


def build(iso: Path, out: Path) -> int:
    if not iso.exists():
        print(f"no such disc image: {iso}")
        return 2
    say = lambda m: print(f"  {m}")  # noqa: E731
    base, entries, blob, ranges = rc._load_tables(iso, say)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    doors = len(rc._door_records(blob))
    hostile = len(rc._hostile_char_blocks(blob))
    print(f"\nwrote {out}  ({len(blob):,} bytes)")
    print(f"  archive base      0x{base:X}")
    print(f"  entries           {entries}")
    print(f"  doors visible     {doors}")
    print(f"  hostile blocks    {hostile}")
    side = out.with_suffix(out.suffix + ".json")
    side.write_text(json.dumps({
        "source_iso": iso.name,          # name only - no path, no hash of game data
        "archive_base": f"0x{base:X}",
        "entries": entries,
        "blob_bytes": len(blob),
        "doors_visible": doors,
        "hostile_blocks": hostile,
        "note": "local measurement fixture - game data - never commit",
    }, indent=2), encoding="utf-8")
    print(f"  sidecar          {side.name}")
    if doors != EXPECTED_DOORS:
        print(f"\nWRONG FIXTURE: expected {EXPECTED_DOORS} doors, saw {doors}.")
        print("That is the stale archive-offset rule. Rebuild with the current engine and do")
        print("not measure anything against this file.")
        return 1
    if len(blob) != EXPECTED_BYTES:
        print(f"\nnote: stream length {len(blob):,} != the recorded {EXPECTED_BYTES:,}.")
        print("Same archive?" + " Check you are pointing at Summoner 1, not Summoner 2.")
    print("\nfixture is good - measure away (not an emulator in sight)")
    return 0


def check(path: Path) -> int:
    if not path.exists():
        print(f"no fixture at {path} - build one with --iso next to your own disc")
        return 2
    blob = path.read_bytes()
    doors = len(rc._door_records(blob))
    hostile = len(rc._hostile_char_blocks(blob))
    chars = len(rc._char_info_blocks(blob)) if hasattr(rc, "_char_info_blocks") else "n/a"
    print(f"{path}")
    print(f"  bytes            {len(blob):,}   (expected {EXPECTED_BYTES:,})")
    print(f"  doors visible    {doors}          (expected {EXPECTED_DOORS})")
    print(f"  hostile blocks   {hostile}")
    print(f"  char blocks      {chars}")
    ok = doors == EXPECTED_DOORS and len(blob) == EXPECTED_BYTES
    print("\nVERDICT:", "usable" if ok else "DO NOT MEASURE AGAINST THIS - rebuild it")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iso", help="your own disc image (never committed)")
    ap.add_argument("--out", default="work/tables_blob.bin", help="where to write the fixture")
    ap.add_argument("--check", metavar="FIXTURE", help="validate an existing fixture instead")
    a = ap.parse_args()
    if a.check:
        return check(Path(a.check))
    if not a.iso:
        ap.error("give me --iso <your disc> or --check <existing fixture>")
    return build(Path(a.iso), Path(a.out))


if __name__ == "__main__":
    raise SystemExit(main())
