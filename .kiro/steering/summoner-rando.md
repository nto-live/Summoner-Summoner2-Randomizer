# Summoner Randomizer — always-on steering

Kiro gets loaded this file on every request in this workspace. Keep it short.

## What this is

A randomizer for **Summoner** (PS2, `SLUS-20074`) and later **Summoner 2** (`SLUS20448`).
Disc in, randomised ISO out, seed shown. Self-contained app, ships no game data. No modding scene
has ever existed for this game — everything here was reverse-engineered from the disc.

**Start here: `KIRO-PROMPT.md`** (repo root). It is the full handoff brief: read-first list, hard
rules, environment traps, verified state, the job queue with acceptance criteria, and the
definition of done. Read it before your first change.

## Non-negotiables

- **No game data, ever** — no ISO, blob, BIOS, texture or extracted stream in the repo or in a
  commit. `python tools/check-no-game-data.py` must print clean before every push.
- **Read the docs before you investigate.** The toolchain, the headless recipe and the door
  mechanism are already written down; re-deriving them has cost days. The dead ends are written
  down too, so they are not retried.
- **Every transform is size-preserving.** Values move only between equal-width fields; names only
  between same-length strings. The `TABLES.VPP` stream's boundaries must not move.
- **Declare and refuse.** State the bytes you expect; abort on mismatch; read back after writing.
  Never guess at a patch.
- **Boot-verified is not play-verified.** Say which one a claim is, every time.
- **Unimplemented means documented as blocked with a reason.** Never half-shipped.
- `F:\rando\S1\iso\` and `F:\rando\S2\iso\` are **read-only**. Builds go to `F:\rando\S1\out\`.
- **Never wipe** the verified ISOs or the parts folders.

## Two traps that will waste your afternoon

1. **PowerShell 5.1 reports stderr as failure.** Add `-q` to every `cli.py` call; a successful build
   otherwise prints "Exec failed". The exit code and the artifact are the truth. Same for `git push`.
2. **PCSX2 headless needs `SettingsVersion = 1` in `PCSX2.ini`** and **`Renderer = 13` (Software)**.
   Get either wrong and you get a silent hang or a PASS that is not actually running. Confirm with
   `churn_scan.py`, never with the boot banner alone.

## The pattern every shipped item follows

Transform in `rando_core.py` → a `Report` with refusals counted, not hidden → mode + option values
merged through `rando_core.mode_options` → **measured** against the disc → `PLANNED.md` row updated
→ committed with the docs in the **same** commit. Commit style:
`lowercase: what changed, and why it is honest`.

## Who tests

**Joshua tests in game, by hand, for now.** Hand him the ISO path, the seed, the exact invocation,
what correct looks like, what a failure looks like, and an honest verification label. Do not claim a
feature works because the build succeeded.
