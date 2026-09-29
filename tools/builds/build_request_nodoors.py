"""A/B test disc: identical to build_request.py BUT with door_destination_remap removed.

Purpose: the REQUEST build (seed REQ1) did NOT drop the burning-village firewall after talking to
the guy, but the earlier CHAOS build did. Both used the same binary patches (skip_intro +
skip_tutorial), so the fire-barrier code path is identical. The transforms differ. The prime
suspect is the door remap disturbing the scripted scene that fires FUN_001DBF50("invis-door02").

This build removes ONLY the door remap and keeps everything else (enemies per_level, xp_scale 200,
enemy_drops_always, skip_intro, skip_tutorial) so a single play tells us if the door shuffle is the
cause. Same seed REQ1 so the non-door transforms produce identical results.
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-REQUEST-NODOORS.iso"
SEED = "REQ1"

transforms = [
    "enemies_random",
    "xp_scale",
    "enemy_drops_always",
]
options = {
    "enemies_random": {"scope": "per_level"},
    "xp_scale": {"percent": 200},
}
binary_patches = [["skip_intro", {}], ["skip_tutorial", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
