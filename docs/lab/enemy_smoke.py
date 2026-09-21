"""Smoke-test the enemy transforms against the extracted TABLES.VPP stream.

  python enemy_smoke.py
"""
import random
import sys

sys.path.insert(0, r"C:\Users\NtO\.openclaw\workspace\tools\summoner-rando")

import rando_core as rc  # noqa: E402

BLOB = r"F:\rando\S1\notes\_end_blob.bin"
blob = open(BLOB, "rb").read()
print(f"blob {len(blob)} bytes")

monsters, peaceful = rc._analyse_enemies(blob)
print(f"placements: {len(monsters)} monsters, {len(peaceful)} peaceful")
hostile = rc._hostile_char_blocks(blob)
print(f"hostile #Character Info blocks: {len(hostile)}")

cases = [
    ("enemies_none", dict(how="navpoint")),
    ("enemies_none", dict(how="team")),
    ("enemies_none", dict(how="both")),
    ("enemies_random", {}),
    ("enemies_swarm", {}),
    ("enemy_difficulty", dict(level="trivial")),
    ("enemy_difficulty", dict(level="hard")),
    ("enemy_difficulty", dict(level="impossible")),
    ("enemy_difficulty", dict(level="normal", level_shift=6)),
]

ok = True
for name, kw in cases:
    fn = rc.TRANSFORMS[name]
    out, rep = fn(blob, random.Random(1234), **kw)
    same = len(out) == len(blob)
    diff = sum(1 for a, b in zip(blob, out) if a != b) if same else -1
    flag = "OK " if same else "SIZE CHANGED"
    if not same:
        ok = False
    print(f"\n{name} {kw}  -> {rep.changed} edits, {diff} bytes differ  [{flag}]")
    for n in rep.notes:
        print(f"    {n}")

print("\nALL SIZE-PRESERVING" if ok else "\n!!! SIZE CHANGED !!!")
