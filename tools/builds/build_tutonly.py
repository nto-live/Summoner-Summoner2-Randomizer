"""Isolation disc: hide_tutorials ONLY, no transforms at all.

Movement froze on the full hide_tutorials build even after I removed all but the two popup-draw
NOPs. That rules out the render side-effects as the cause. This strips EVERYTHING else so we test
one variable: does the two-nop tutorial patch alone freeze the opening, or is it something in the
transform stack (door remap / enemies / xp / drops)?

- If the guy MOVES here -> the tutorial patch is innocent; a transform froze him (suspect doors).
- If the guy STILL can't move -> the tutorial render nops themselves break the opening; back off.

Retail content otherwise. skip_intro included only so we don't sit through the logos each test.
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-TUTONLY.iso"
SEED = "TUT1"

transforms = []          # nothing
options = {}
binary_patches = [["skip_intro", {}], ["hide_tutorials", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
