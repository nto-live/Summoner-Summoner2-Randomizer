---
inclusion: auto
name: project-memory
description: Durable memory for the Summoner randomizer — verified state, environment facts, the Ghidra/emulator rig, hard-won gotchas, and where things live. Load when working on transforms, doors, the binary layer, the emulator, or picking up prior work.
---

# Summoner Randomizer — project memory

Living record of what is known-true, so it is not re-derived. Pairs with the always-on
`summoner-rando.md` (the rules) and `docs/SESSION-PROGRESS.md` / `docs/TODO.md` (the log + backlog).
Update this when a fact changes.

## What the app is

Disc-in → randomised-ISO-out for **Summoner** (PS2, `SLUS-20074`). Ships no game data. Engine is
Python in `src/` (`cli.py` front door, `rando_core.py` transforms, `binary.py` ELF patches,
`discover.py` ISO/VPP parsing). Desktop UI is C# in `desktop/` and is **data-driven off
`cli.py --list`** — new transforms surface automatically once registered.

## Environment facts (this machine — Windows on ARM, PowerShell)

- Retail ISO (read-only): `C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso`
- Build output dir: `C:\temp\NTO_Live_Code\out\` — combined disc `Summoner-CHAOS.iso`, wrapper
  `out/build_chaos.py`.
- **Ghidra**: `C:\temp\ghidra-tools\ghidra_12.1.3_PUBLIC` + EE extension `ghidra-emotionengine-reloaded`.
  JDK 21 at `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot`. Set `JAVA_HOME` before use.
  Project copy: `C:\temp\ghidra-work` (name `SummonerEE`, program `SLUS_200.74`, r5900:LE:32,
  image base `0x00100000`). Run: `analyzeHeadless.bat "C:\temp\ghidra-work" SummonerEE -process
  SLUS_200.74 -readOnly -noanalysis -scriptPath C:\temp\ghidra-work\scripts -postScript X.java`.
  **The headless decompiler returns EMPTY here — use disassembly (instructions/refs), not decomp.**
  The project was owner-locked; the local copy's `project.prp` OWNER was reset to the local user.
- **PCSX2**: `C:\Program Files\PCSX2\pcsx2-qt.exe`, dedicated datapath `C:\temp\pcsx2-data`
  (BIOS `ps2-0230a-20080220.bin`). Boot: `QT_QPA_PLATFORM=windows`, `-batch -fastboot -datapath ...`.
  emulog at `C:\temp\pcsx2-data\PCSX2\logs\emulog.txt`. Churn check: `docs/lab/churn_local.py`
  (PINE on 28011). PASS banner ≠ running — confirm with churn (~2 blocks = frozen, ~25 = live).

## Gotchas that cost time (do not relearn)

1. **PowerShell eats `$` in inline `python -c`** — write a `.py` file in `docs/lab/` instead.
2. **PowerShell treats native stderr as failure** — add `-q` to `cli.py`; trust exit code + artifact.
3. **`git push` / native tools** print progress to stderr → shows red but exit 0 = success.
4. **PCSX2 `-datapath` writes to a `PCSX2\` SUBDIR**, not the datapath root — ini/bios/logs live there.
5. **The background-terminal tool can "reuse" a dead handle** and not actually relaunch PCSX2 — if no
   emulog appears, stop the terminal and start fresh (or run via execute with run_in_background).
6. **PCSX2 holds the ISO open** — kill `pcsx2-qt` before rebuilding the same output ISO (else
   `PermissionError`).
7. **`binary.py` `blocked=` line kept reappearing** across edits — verify it's gone after editing
   `skip_intro` (clear `src/__pycache__`).

## Verified state (as of 2026-09-28)

- **skip_intro** (binary, `0x002419C0` → `jr $ra` + `li v0,1`): **play-verified** — THQ `.pss` logo
  gone. Does NOT touch the in-engine story cutscene (that hangs if neutered; it's button-skippable).
- **Transforms added & build-verified** (size-preserving, registered, in UI): `weapon_attack_max`,
  `armor_protect_max`, `enemy_drops_random`, `enemy_drops_always`, `enemy_xp_random`, `enemy_xp_set`,
  `music_tracks_shuffle`. Plus the pre-existing `enemy_hp_set`, `item_scatter`, `chest_items`, etc.
- **door_destination_remap**: quote-corruption FIXED; `+Index` slot check + `+Script` safe-target
  rule added. 151 interior doors remap. **Overworld/masad doors are HELD** (`DOOR_SOURCE_EXCLUDE`)
  because they bounce to the title even when statically valid — the hub load path is not understood.

## Key reverse-engineered facts

- **Doors**: a `$Trigger:"<name>" +Id:"load level"` block; the NAME is the destination. Rewrite the
  quoted name in place, `new + spaces + '"'`, len(old)+1 bytes. Constraints: real `Level_info` name;
  `len(new)<=len(old)`; `+Index` slot must exist in dest (`$player*-N` navpoint); no-`+Script` door
  must target a level whose script == its name. Full mechanism: `docs/lab/door-mechanism.md`.
  Safe-target data: `docs/lab/level_scripts.json` (50/51 safe, only `endgame` isn't).
- **Level→script map**: `script_filenames.tbl` in TABLES.VPP (banner "CHANGING THE ORDER" → `#End`).
- **Gear**: weapons carry `$Damage` (+ adjacent `$Damage Type` marker); armour records start `$Armor:`
  with `$Protection`. Both distinct from creature `$Damage`/`$Protection` in `#Character Info`.
- **Enemy XP on kill** = `$Experience Gained` inside hostile `#Character Info` blocks (109/80).
- **Drops** = `+Drop: "Item" <chance 2..100>`, attached to attack/death records, not the stat block.
- **Tutorial (BLOCKED — proven in game, do NOT re-attempt without a new mechanism)**:
  17-step STATE MACHINE (step fns `0x0023C868`..`0x0023D4A8`, table `0x0127DEE8` stride 0x24),
  dispatcher `FUN_0023D618`, ignore-global `gp-0x3A70` (debug toggle handler `0x0023C808`). The
  dispatcher drives BOTH the tutorial popups AND the advance of the opening scripted scene
  (burning-village intro) through the SAME path. Three resolved patches were each built + booted;
  ALL break the game — v1 ignore-global on (`0x0023D648`→`li v0,1`): firewall soft-lock; v2 NOP
  activation (`0x0023D6B4`): intro stalls; v3 auto-advance (`0x0023D74C`→nop): intro stalls. A
  CONTROL disc without the patch plays fine, so the patch is the cause. No separable display-only
  chokepoint exists. `skip_tutorial` is `blocked=` in binary.py (refuses/writes nothing) and out of
  the build. Full write-up: `docs/RESEARCH-SKIP-TUTORIAL.md`. Never patch shared `flag_is_set`
  `0x001F10A8` / `flag_set` `0x001F11E8` (all game flags route through them).

## Where the open work is

`docs/TODO.md` — prioritised, every wanted feature with status and next step. `docs/PLANNED.md` §3 —
the BLOCKED table with reasons. Joshua tests in game by hand; hand him ISO path + seed + invocation +
what-correct-looks-like + honest verification label.
