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
- **Enemy XP on kill** = `$Experience Gained` in hostile `#Character Info`. (dup line above; keep one.)
- **Tutorial off — use `skip_tutorial` (NOP the input-gate). This is THE working patch.** Mechanism
  (proven, `docs/lab/ANALYSIS-why-v3-works.md`): dispatcher `ngps_process_tutorial` @`0x0023d618`
  runs the active step then a tail that polls the pad and only calls the step-ADVANCE
  (`jal 0x0023d5f0` @`0x0023d754`) when the taught button was pressed (`s0=1`), gated by
  `0x0023D74C beq s0,zero,0x0023d760`. **`skip_tutorial` NOPs that gate** (`0x12000004`→0) so the
  advance runs every frame with no input → steps auto-complete, popups don't hold you, scene
  actions still run. PLAY-VERIFIED: no tutorials, player moves, fire drops. Minor quirk: auto-advance
  can pass the dialogue step before the CONVERSATION sets `masad_dialogue_tutorial_part2b` (the flag
  that gates the fire removal), so you may talk to the opening NPC 2-3× for the fire to drop — not a
  soft-lock. Now labelled the working patch in `binary.py` (un-blocked, not experimental).
  - **`hide_tutorials` is a DEAD END (blocked in binary.py).** It NOPs the two draw calls in
    `ngps_render_tutorial` (`0x0023d824` box, `0x0023d8c0` text) so the popup window is hidden, BUT
    it leaves the input-gate at `0x0023d74c` intact → the step still WAITS for the button + plays its
    sound, so the player is frozen at the start with no instructions. Worse UX. Wrong lever.
  - **Dead ends (do NOT retry):** early-return whole `ngps_render_tutorial` @`0x0023d780` = FROZE the
    opening (its per-frame `sw v0,-0x3360(gp)` @`0x0023d8d4` is load-bearing). v1 force ignore-global
    `0x0023D648`→li v0,1 = soft-lock. v2 NOP activation `0x0023D6B4` = stall. Never patch shared
    `flag_is_set` `0x001F10A8` / `flag_set` `0x001F11E8`.
  - **RESOLVED false alarms:** `enemies_random scope=per_level` does NOT break the fire (earlier
    "froze"/"fire didn't drop" was just not talking to the NPC enough times — retracted). The fire
    barrier `invis-door02` is removed by the executable via a HARDCODED string, so
    `door_name_shuffle` could rename its record and soft-lock the opening — now FIXED: `invis-door0N`
    are pinned in `t_door_name_shuffle` (verified across 8 seeds, `docs/lab/verify_door_pin.py`).
- **Fire barrier `invis-door02`**: removed inside the dialogue-tutorial step
  (`jal 0x001dbf50("invis-door02")` @`0x0023cb6c`), gated on `flag_is_set(masad_dialogue_tutorial_
  part2b)` which the CONVERSATION sets. Full analysis: `docs/lab/ANALYSIS-invis-door02-fire-barrier.md`.
- **Known-good shipping recipe:** `skip_intro` + `skip_tutorial` + the transform stack (see
  `tools/builds/build_chaos.py`). Play-verified as CHAOS2.

## Where the open work is

`docs/TODO.md` — prioritised, every wanted feature with status and next step. `docs/PLANNED.md` §3 —
the BLOCKED table with reasons. Joshua tests in game by hand; hand him ISO path + seed + invocation +
what-correct-looks-like + honest verification label.

## Update 2026-09-30 — boss rush BLOCKED, two new transforms, Tested/Experimental UI

- **Boss rush / gauntlet is BLOCKED (proven, do not re-chase).** Full write-up:
  `docs/BOSS-RUSH-INVESTIGATION.md`. The wall: bosses are hidden/scripted set-pieces, NOT
  placement-registered, so placing them as live enemies faults the engine name-lookup (TLB miss
  reading `0x72616863` = "char" — a $Character string used as a pointer); boss levels' NPCs are all
  scene-critical (overwriting/unlinking freezes the scene script); cross-level remapped doors render
  mid-story levels black. Modes `boss_rush` / `boss_rooms` / `boss_gauntlet` are `buildable:False`.
- **Hard rules (now proven in game):** (1) `$Character`/door-dest swaps EQUAL-LENGTH only — space
  padding corrupts the record → "char" TLB freeze. (2) only place creatures the level loads as an
  active `+Monster` (hidden/`+Boss` crash; unloaded models → black/hang). (3) never overwrite/unlink
  scene-critical NPCs (name referenced elsewhere). (4) `endgame` is not a door target (no start
  slot); mid-story levels (sewerboss) render black via remapped doors.
- **New working transforms:** `gold_max` (gold containers → field max 999/99/9; gold is
  container-only, enemies can't drop gold), and `door_destination_remap` now has a `scope` option
  (`interior` default / `overworld` / `all`). Boss→level map = VPP member filename (TABLES.VPP TOC
  via `VppFile`), not inline text.
- **UI honesty:** modes carry a `tested` bool (default False). Desktop groups modes into **Tested**
  (play-verified: `vanilla_no_tutorial`, `tested_chaos`) vs **Experimental (untested)** tabs, plus a
  disabled **Summoner 2 — TBD** tab. `docs/TESTING-HELP-WANTED.md` is the play-testing ask.
- **Roguelike** mode is also `buildable:False` (eleven unverified changes).
