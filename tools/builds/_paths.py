"""Shared paths for the build scripts.

These scripts live IN the workspace (so they can be edited freely and tracked in git), but they
read the retail ISO and write built ISOs to the machine's data dir OUTSIDE the repo - game data
never enters git. Adjust the two externals here if the machine layout changes.
"""
import os
import sys
from pathlib import Path

# repo root = two levels up from tools/builds/
REPO = Path(__file__).resolve().parents[2]
SRC_DIR = REPO / "src"
sys.path.insert(0, str(SRC_DIR))

# external, machine-local data (never in the repo)
DATA = Path(r"C:\temp\NTO_Live_Code")
SRC_ISO = DATA / "Summoner (USA)" / "Summoner (USA).iso"
OUT_DIR = DATA / "out"
OUT_DIR.mkdir(exist_ok=True)


def progress(msg):
    print(f"  {msg}", flush=True)


def summarize(res, out_path, seed):
    print("\n=== BUILD SUMMARY ===")
    print("out:", out_path, "seed:", seed, "size preserved:", res.get("size_preserved"))
    for r in res.get("reports", []):
        print(f"  {r.get('transform'):<24} changed={r.get('changed')}")
    for b in res.get("binary", []):
        print(f"  binary {b.get('patch'):<16} applied={b.get('applied')}")
