# The `+Script:` rule for door remapping — authoritative level→script map

Workstream: randomizer — door destinations. Disc: retail `Summoner (USA).iso` (read-only).
Companion data: `level_scripts.json` (this folder). Regenerate: `python docs/lab/build_level_scripts.py`.

**Verification label: STATIC/DATA-verified.** Everything here was read out of `TABLES.VPP` on the
retail disc and cross-checked against `door-mechanism.md`. Nothing was play-verified; no emulator
was run. See §6.

---

## 1. The blocker, in one sentence

`t_door_destination_remap` (`src/rando_core.py`) only remaps the **90** doors that carry an
explicit `+Script:` and holds the **128** that don't, because a no-`+Script:` door uses its
**destination name** as the script name, and if the target level doesn't provide a script by that
name the load resolves to nothing → "Exit to Unknown" → bounce to menu (`door-mechanism.md` §5b
caveat 2). To lift that hold safely we need the authoritative *which script filenames each level
provides*. That is what this deliverable produces.

## 2. Where the authoritative map lives, and how it was parsed

The engine fills `Level_script_info` (`0x121EB70`, 51 records × 0x70) at runtime from a disc file
**`script_filenames.tbl`** (`level_script_load_script_filename_table` @ `0x001EAAF8`,
`door-mechanism.md` §2). That file is a member of `TABLES.VPP`.

Locating it precisely (not the 191 other scattered `$Level:` lines in per-level `.tbl`/dialogue
members):

- `TABLES.VPP` is a v1 packfile at ISO `0x49086800`. Its directory is a flat array of **0x40-byte
  records** starting at VPP `0x800`: name at `+0x00` (null-padded), **u32 file size at `+0x3C`**.
  `count` (527) is the header field at `+0x08`. The directory confirms a member literally named
  `script_filenames.tbl` (size `0x1EBC` = 7868 bytes).
- The file's **body** is a single contiguous table of tightly-packed `$Level:` records (each
  followed by `+Script:` / `+Dialogue:` / `+Levelcap:` lines), which is unmistakable against the
  per-level files that carry one lone `$Level:` tens of KB apart. It is preceded by the shipped
  warning banner `// CHANGING THE ORDER IN WHICH THE SCRIPTS APPEAR ...` and terminated by `#End`.
- We parse **only** the slice between that banner's first `$Level:` and the `#End` marker, at
  VPP `0x5920C8..0x593EB8` (ISO `0x496188C8..`). Record grammar:

  ```
  $Level:   "Catacombs"
  +Script:  "catacombs"      <- FIRST +Script: = the base/default (Level_script_info index 0)
      +Dialogue: 1 5
      +Levelcap: 10
  // comment                 (optional, ignored)
  +Script:  "catacombs_v2"   <- additional scripts (indices 1..6)
  ```

The parse yields **51 `$Level:` records**, matching `door-mechanism.md` §3's 51-level `Level_info`
inventory **exactly** (0 missing, 0 extra). That equality is the correctness anchor.

## 3. The rule

For a door with **no** `+Script:`, the engine calls
`level_script_get_level_script_index(level, destination_name)` (`0x001EAD98`), which searches that
level's script list (`Level_script_info[level][0..6]`) with `ngps_stricmp` and returns -1 if none
match. So:

> **A no-`+Script:` door can safely target level L iff L provides a script whose name equals L's
> level name, case-insensitively.**

Case is free (`ngps_stricmp`): `IonaExt` provides `IonaEXT`, `lenele3d` provides `Lenele3d`,
`Wolong` provides `wolong`, `KhosaniLab` provides `khosanilab` — all SAFE. In the shipped data the
matching script is always the **base** (index-0) script; `base_is_name` and `provides_name_script`
agree for every level. `level_scripts.json` records both flags plus the full ordered script list
per level.

## 4. The safe-target set

**50 of 51 levels are safe** no-`+Script:` targets. The lone exception is **`endgame`**, which has
**no `+Script:` at all** (empty script list) — so a no-script door pointing at it would resolve to
nothing. `endgame` is already in `DOOR_TARGET_EXCLUDE` (the Forge is never a remap target), so in
practice the safe set for remapping is:

> **Every `Level_info` level except `endgame` and `test`** (`test` being the excluded dev level).

Safe levels (50): `Catacombs, eleh, IkaemosBottomInt, IkaemosBottomInt2, IkaemosExt, IkaemosExt2,
IkaemosTopInt, IonaExt, IonaExt02, jadetemple, KhosaniLab, KhosaniLab2, KhosaniStrng, lenele1aa,
lenele1ab, lenele1b, lenele1c, lenele1d, lenele1e, lenele2aa, lenele2ab, lenele2d, lenele3a,
lenele3d, Liangshan, LPalaceInt, LPalaceInt02, masad, Rand-Desert, Rand-DesertNite01, rand-forest01,
rand-forestnite1, Rand-Grassland01, Rand-GrasslandNite01, rand-hills01, Rand-HillsNite01,
Rand-Iceland01, Rand-IcelandNite01, Rand-Orenia01, Rand-OreniaNite01, sewer, sewerboss, tancredhouse,
TempleInt, TempleInt2, test, Wolong, Wolong2, WolongCaverns, worldmap1`.

Unsafe (1): `endgame`.

## 5. Cross-check against the 128 no-script doors (`transitions.json`)

| doors | count |
|---|---|
| total | 218 |
| with explicit `+Script:` | 90 |
| **no `+Script:`** | **128** |
| — targeting a SAFE level | **128** |
| — targeting an UNSAFE level | 0 |
| — targeting a dest not in the 51-level table | 0 |

Every currently-shipped no-script door already points at a safe level, which is consistent with the
rule being an invariant the developers relied on (`door-mechanism.md` §5b: "all such blocks rely on
it").

## 6. What this means for wiring the constraint (for the owner — no code was changed)

The `+Script:` blocker is far less restrictive than a full hold. To remap the 128 no-script doors,
constrain each such door's target to the **safe set in §4** (i.e. exclude only `endgame`, on top of
the existing length / self-level / exclude / start-slot constraints). Because 50/51 levels are safe,
this unlocks essentially the full target pool for no-script doors — the only extra rule is "a
no-script door must not target `endgame`", which the existing `DOOR_TARGET_EXCLUDE` already enforces.

Concretely, the safe-target predicate is: `level_scripts.json["levels"][dest]["safe_no_script_target"]`.
A door that already carries an explicit `+Script:` is unaffected by this rule (its script travels
with it), so those 90 keep their current freedom.

### Honest limits

- **STATIC/DATA-verified only.** This is a read of the disc plus a decompiled-logic argument; no
  door has been walked, no build booted. The `+Index:` player-start caveat (`door-mechanism.md` §5b
  caveat 1) is a **separate** constraint already handled by `_level_start_slots`; this deliverable
  does not touch it.
- The safety boolean is derived from `ngps_stricmp` semantics (plain case-fold). If the engine's
  comparison were ever not a pure case-fold (it is, per the decompile), a name differing only by
  punctuation could be misjudged — but no such case exists in the 51 records; every safe level
  matches by case-fold alone.
- `level_scripts.json` contains level names and script **filenames** only (derived metadata, same
  class as `door-triggers.json` / `transitions.json`). No game bytes are stored. `check-no-game-data.py`
  is clean.
