#!/usr/bin/env python3
"""Guard: fail if the repo contains verbatim game material.

The project rule is that nothing extracted from the game goes into the repository - no assets,
no dialogue, no script blocks, no bulk dumps. Format *keys* (`+Monster`, `$Trigger:`) and
factual metadata (level names, counts, offsets) are how a format gets documented, so those are
allowed; long verbatim runs copied out of the game's files are not.

This scans every file git tracks and reports any run of characters that also appears verbatim in
the game's text stream. The stream is the extracted `TABLES.VPP` payload, which only exists on a
developer machine; without it the script still checks the obvious things (disc images, big files,
binary extensions) and says so.

    python tools/check-no-game-data.py
    python tools/check-no-game-data.py --blob "F:\\rando\\S1\\notes\\_end_blob.bin" --min-run 60

Exit code 0 clean, 1 something to look at.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_BLOB = r"F:\rando\S1\notes\_end_blob.bin"

# Extensions that have no business in this repository at all.
FORBIDDEN_EXT = {".iso", ".bin", ".vpp", ".p3d", ".s3d", ".tbl", ".pss", ".irx", ".img",
                 ".mvf", ".peg", ".exe", ".dll", ".pdb", ".ps2", ".sav", ".gsd", ".p2s"}
TEXT_EXT = {".py", ".md", ".txt", ".json", ".cs", ".ps1", ".cmd", ".html", ".sln", ".csproj",
            ".user", ".gitignore", ""}
BIG_FILE_BYTES = 200_000


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def longest_verbatim(text: str, blob: bytes, min_run: int) -> tuple[str, str]:
    """The longest window of `text` that occurs verbatim in the game stream.

    Lines made of filler (rules of dashes, box drawing, plain separators) are skipped: they
    collide with the stream's zero padding and mean nothing. A line has to carry real words to
    count as copied content.
    """
    best = ""
    for line in text.splitlines():
        s = line.strip()
        if len(s) < min_run or not s.isprintable():
            continue
        alnum = sum(c.isalnum() for c in s)
        if alnum < 12 or alnum < 0.6 * len(s):
            continue
        step = max(1, min_run // 2)
        for i in range(0, len(s) - min_run + 1, step):
            window = s[i:i + min_run]
            if window.encode("latin-1", "ignore") in blob:
                # extend the match while it keeps matching, for a useful report
                end = i + min_run
                while end < len(s) and s[i:end + 1].encode("latin-1", "ignore") in blob:
                    end += 1
                if len(s[i:end]) > len(best):
                    best = s[i:end]
    return best, best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repository root")
    ap.add_argument("--blob", default=DEFAULT_BLOB, help="extracted game text stream, for the check")
    ap.add_argument("--min-run", type=int, default=60, help="shortest verbatim run that matters")
    a = ap.parse_args()

    root = Path(a.root).resolve()
    blob = b""
    if Path(a.blob).is_file():
        blob = Path(a.blob).read_bytes()
        print(f"reference stream: {a.blob} ({len(blob)} bytes)")
    else:
        print(f"reference stream: NOT FOUND ({a.blob}) - only the structural checks will run")

    problems: list[str] = []
    files = tracked_files(root)
    print(f"scanning {len(files)} tracked file(s)\n")

    for rel in files:
        p = root / rel
        if p.is_dir():
            continue
        suffix = p.suffix.lower()
        if suffix in FORBIDDEN_EXT:
            problems.append(f"{rel}: forbidden file type {suffix}")
            continue
        size = p.stat().st_size
        if size > BIG_FILE_BYTES:
            problems.append(f"{rel}: {size:,} bytes - too big for source; is this a generated file?")
        if suffix not in TEXT_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            problems.append(f"{rel}: unreadable ({e})")
            continue
        if blob:
            run, _ = longest_verbatim(text, blob, a.min_run)
            if len(run) >= a.min_run:
                snippet = run[:70].replace("\n", " ")
                problems.append(f"{rel}: {len(run)}-char verbatim run from the game: {snippet!r}")

    if problems:
        print("FOUND:")
        for p in problems:
            print(f"  - {p}")
        print(f"\n{len(problems)} item(s). Take them out, or explain in NOTICE.md why they stay.")
        return 1

    print("clean: no game material, no disc images, no oversized files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
