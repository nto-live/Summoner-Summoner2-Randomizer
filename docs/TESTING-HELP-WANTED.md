# Help wanted: play-testing

This randomizer is built and verified by hand, one disc at a time. Most of the engine is
**boot-verified** at best (it builds a valid disc) but **not play-verified** (nobody has played it
through in-game). We need help confirming what actually works. If you have Summoner (PS2,
SLUS-20074) and an emulator or console, you can help a lot.

The project rule is: **boot-verified is not play-verified.** A mode only moves from the
"Experimental" tab to the "Tested" tab after someone plays it and confirms it behaves.

## What is already play-verified (the "Tested" tab)

- **Vanilla · No Tutorials** — retail game with only the opening tutorials turned off.
- **Tested · No Tutorial + 1HP + Random Loot** — the "CHAOS" recipe: tutorials off, enemies
  randomized within their own area, every enemy dies in one hit, random drops + maxed gold,
  boosted XP. Confirmed to boot, move, and progress past the opening.
  - Known quirk (not a bug): at the burning village, talk to the first NPC a couple of times for
    the fire to drop. This is a side effect of the tutorial-skip and is non-blocking.

## What needs testing (everything in the "Experimental (untested)" tab)

Every other mode builds a size-valid disc but has NOT been played through. The highest-value ones
to test, roughly in order:

1. **Door Remap** — rewrites where doors lead. Does the game stay completable, or does a door
   strand you / bounce to the title / load a black room? Note the seed and where it broke.
2. **Door Shuffle** — locks/names/sounds shuffled. Should be safe; confirm nothing soft-locks.
3. **Short Run / One Hour** — pacing (cutscenes skipped, XP scaled). Does it play to the end?
4. **No Enemies / Enemy Swarm / Oops All Enemies** — enemy count levers. Do quests still work?
5. **Monster Chaos / Random Enemy Stats / stat modes** — combat balance. Winnable? Soft-locks?
6. **Item Scatter / Shop / Chest / Item Hunt** — loot placement. Does anything required become
   unreachable?
7. **Random Rooms / NPC Hunt** — placement shuffles within a level.

## What is BLOCKED (do not expect these to work)

- **Boss Rush / Boss Rooms / Boss Gauntlet** — exhaustively attempted and proven unachievable in
  the data (bosses are hidden/scripted set-pieces, not placeable as live enemies). Full analysis:
  `docs/BOSS-RUSH-INVESTIGATION.md`.
- **Roguelike** — stacks eleven unverified changes; marked blocked pending validation.

## Summoner 2 (SLUS-20448) — TBD

Not implemented yet. The tool randomizes Summoner 1 only. The "Summoner 2 — TBD" tab in the UI is a
placeholder marker, not a working target.

## How to report a result

For each mode you test, please note:

- **Mode name** and **seed** (both shown in the UI; the seed is in the output ISO name too).
- **Did it boot?** Reach the main menu / first playable frame?
- **Did it play through?** How far did you get before any problem.
- **What broke, exactly** — freeze (black screen? loading bar stuck?), bounce to title, missing
  enemies/NPCs, a quest that can't complete, etc. Include the level/area name and what you were
  doing.
- **A screenshot** of any freeze/black screen is extremely helpful (it often shows the cause).

Open an issue on the repo with that information, or drop it wherever the project collects feedback.
A result of "played mode X on seed Y start to finish, no problems" is just as valuable as a bug —
it's how a mode earns its place in the Tested tab.

Thank you. Every play-test turns a guess into a fact.
