"""Isolate the freeze: full request set MINUS door_destination_remap, WITH hide_tutorials.

Established: tutorial-only disc (Summoner-TUTONLY) let the guy move and dropped the fire. The full
request disc (Summoner-HIDETUT) froze movement. So a TRANSFORM freezes the opening. door remap is
the prime suspect (it can rewrite the start-level spawn navpoint). This build keeps everything
except doors:
  hide_tutorials + skip_intro, enemies_random per_level, xp_scale 200, enemy_drops_always
  NO door_destination_remap.

- Guy MOVES here -> the door remap is the freeze; fix it to leave the start level's spawn alone.
- Guy STILL frozen -> a different transform (enemies/xp/drops) is at fault; bisect further.

Seed REQ1 so non-door content matches the discs already tested.
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-NODOORS-TUT.iso"
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
binary_patches = [["skip_intro", {}], ["hide_tutorials", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
