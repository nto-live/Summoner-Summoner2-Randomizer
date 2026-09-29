# Session progress — 2026-09-28

A running log of what was built, verified, and left open in this session. Verification labels
follow the project rule: **build-verified** (engine says applied, size preserved, changes
confined), **byte-verified** (bytes read back on disc), **boot-verified** (emulator reaches
gameplay), **play-verified** (watched happening in game). Say which one, every time.

## Headline

Built one combined "CHAOS" disc from the retail image with a big stack of options, and added
several new transforms to the engine. Disc: `C:\temp\NTO_Live_Code\out\Summoner-CHAOS.iso`
(seed `CHAOS1`, built via `out/build_chaos.py`). All edits are size-preserving.

## New transforms added this session (`src/rando_core.py`)

| Transform | What it does | Option | Verified |
|---|---|---|---|
| `weapon_attack_max` | sets every weapon's `$Damage` high (clamped per field) | `value` (default 999) | build-verified, byte-verified on disc |
| `armor_protect_max` | sets every armour item's `$Protection` high | `value` (default 999) | build-verified, byte-verified |
| `enemy_drops_random` | shuffles which item each `+Drop` yields | — | build-verified |
| `enemy_drops_always` | maxes existing `+Drop` chances to 100 (guaranteed) | — | build-verified |
| `enemy_xp_random` | shuffles `$Experience Gained` among hostiles | `style` floor/pure | build-verified |
| `enemy_xp_set` | sets every enemy's kill XP to a value (fast leveling) | `value` (default 9999) | build-verified |
| `music_tracks_shuffle` | shuffles background music `$Soundtrack` only (not SFX) | — | build-verified |

All are registered in `TRANSFORMS`, `TRANSFORM_INFO`, `OPTIONS`, `OPTION_AWARE`, and classified in
the desktop UI `Gameplay` set (`MainForm.cs`), so they surface in the app automatically (the UI is
data-driven off `cli.py --list`).

## skip_intro (binary) — the .pss logo movies

`binary.py`'s `skip_intro` was resolved and un-blocked earlier and is now applied by the build
(`0x002419C0` → `jr $ra`, delay slot `li v0,1`). **play-verified:** the THQ logo no longer plays
(Joshua confirmed in game). The `blocked=` line was removed so it writes for real.

**Important scope:** this only removes the `.pss` FMV logos (THQ / attract demo / Volition). The
in-engine **story cinematic** (the narrated opening over `masad`) is a separate `$Cutscene` and is
NOT removed — neutering that token hangs the boot (tested). It is button-skippable in game.

## door_destination_remap — the big fix and the honest limit

The headline door feature had two real bugs found in game this session:

1. **Quote corruption (FIXED).** Rewrites were writing `new + '"' + spaces`, leaving the original
   closing quote dangling → malformed destination → silent failure. Corrected to
   `new + spaces + '"'` (the documented-correct layout).
2. **`+Index` start-slot (half-fixed).** A door arrives at `+Index: N`; the destination must have a
   `$player*-N` navpoint or the load fails. Added `_level_start_slots()` + a slot check. The map
   only resolves ~21/51 levels (conservative), so some doors are skipped rather than risked.
3. **`+Script` rule (FIXED via sub-agent).** 128 of 218 doors have no `+Script:`, so they use the
   destination NAME as the script; the target must provide a script equal to its name or it bounces
   to "Exit to Unknown". Parsed the authoritative `script_filenames.tbl` → `_no_script_safe_targets`
   (50 of 51 levels are safe; only `endgame`, already excluded). See `docs/lab/DOOR-SCRIPT-RULE.md`
   and `docs/lab/level_scripts.json`.

**The overworld problem (HELD, unresolved).** Even after all three fixes, the **masad boat and the
22 overworld (`worldmap`) doors still bounced to the title screen** in game — despite passing every
static check (valid name, length, `+Index` slot present, `+Script` safe). The overworld hub uses a
load path we cannot validate from the tables. So `DOOR_SOURCE_EXCLUDE = {masad, worldmap, worldmap1}`
now **holds those doors unchanged**. Result: **151 interior doors randomized**, overworld left
vanilla. This is the conservative call — a stranded first boat ride is game-breaking.

Coverage summary: 218 total → 151 remapped, ~44 skipped (`+Index` slot gaps), 23 held (overworld).

## Tutorial disable — mechanism found, NOT patched

Investigated in Ghidra. The `masad_*_tutorial` names are `+Flag:` declarations; the trigger logic
is in the ELF/script layer, not the text tables. Found:
- gate `FUN_0023c8f0` → `flag_is_set` (`0x001f10a8`, nonzero = already shown = skip) → else fire +
  `flag_set` (`0x001f11e8`, a3=1). Fire-once pattern.
- an `Ignore tutorial` debug command (string `0x0127dec0`, table entry `0x0023da14`).

No single safe switch found: only one hardcoded gate references the flag strings directly (the rest
are data/script-driven), and the debug command routes through a generic registrar, not a plain
global. **Not patched** — a multi-site or script-layer edit that must be play-verified, and rushing
it risks the same boot hang the cutscene neuter caused. Full detail in `PLANNED.md` §3.

## Lab artifacts created (all in `docs/lab/`, names/metadata only — no game data)

- `transitions.json` + `export_transitions.py` — all 218 doors (offset, src, dest, +Index, +Type,
  has_script, script) + per-level start slots.
- `level_scripts.json` + `build_level_scripts.py` — authoritative level→script map, safe-target set.
- `DOOR-SCRIPT-RULE.md` — the +Script rule write-up.
- probe scripts: `probe_xp.py`, `probe_drop_force.py`, `probe_worldmap_doors.py`,
  `probe_worldmap_special.py`, `check_masad_in_build.py`, `probe_level_scripts.py`.

## What Joshua should test (next session)

1. **First boat transition** — should now go to the overworld normally (no "Exit to Unknown" → title).
2. **Interior doors** — 151 randomized; deeper transitions should surprise.
3. **Fast leveling** — enemies give 9999 XP; kill one, confirm level jumps.
4. **Guaranteed drops / 1-HP enemies / buffed gear** — as designed.
5. **Movies** — THQ logo gone; story intro still needs a manual button-skip.
