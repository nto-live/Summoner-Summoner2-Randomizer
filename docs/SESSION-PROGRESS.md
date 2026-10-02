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

---

# Session progress — 2026-09-29

The tutorial-off day. Goal reframed by the user: this is a tool a stranger runs through the UI to
make a randomised ISO, so tutorial-off must be RELIABLE, not a recipe that limped through once.

## Headline

**Understood and fixed tutorial-off.** `skip_tutorial` (NOP the dispatcher input-gate at
`0x0023D74C`) is THE working patch: tutorials auto-advance with no button press, the opening plays
through, the player can move, and the burning-village fire drops. Proven by disassembly
(`docs/lab/ANALYSIS-why-v3-works.md`) and play. Also closed a real end-user soft-lock:
`door_name_shuffle` could rename the fire barrier `invis-door02` (the engine removes it by hardcoded
string) — now pinned. Rebuilt the CHAOS disc with `skip_tutorial` + the full stack.

## What we learned (the mechanism, finally grounded in disassembly)

- The tutorial is a 17-step machine. The dispatcher `ngps_process_tutorial` (`0x0023d618`) advances
  the active step (`jal 0x0023d5f0` @`0x0023d754`) ONLY when the taught button was pressed that
  frame (`s0=1`), gated by `0x0023D74C beq s0,zero,0x0023d760`.
- **`skip_tutorial`** NOPs that gate → advance runs every frame with no input → tutorials
  auto-complete, popups don't hold you, scripted scene-actions still run. Correct lever.
- **`hide_tutorials`** (NOP the two draw calls in `ngps_render_tutorial`) hides the popup window but
  leaves the input-gate → player frozen at the start with no instructions. WRONG lever; now blocked.
- Fire barrier `invis-door02` is removed inside the dialogue-tutorial step, gated on
  `masad_dialogue_tutorial_part2b`, which the CONVERSATION sets — hence "talk to the NPC 2-3 times"
  (auto-advance can pass the dialogue step before the flag is set). Minor, non-blocking quirk.

## Changes shipped this session

| Change | File | Verified |
|---|---|---|
| `skip_tutorial` promoted to the working patch (un-blocked, relabelled) | `src/binary.py` | byte-verified; play-verified as CHAOS2 |
| `hide_tutorials` marked dead-end + `blocked` (refuses to apply) | `src/binary.py` | verified via `cli.py --list` |
| `door_name_shuffle` pins `invis-door0N` (fixes opening soft-lock in Door Shuffle / Everything modes) | `src/rando_core.py` | verified across 8 seeds (`docs/lab/verify_door_pin.py`) |
| "No progression risk" blurb on Door Shuffle mode corrected | `src/rando_core.py` | — |

## Dead ends confirmed (do NOT retry)

- Early-return whole `ngps_render_tutorial` (`0x0023d780` → jr ra) = froze opening (load-bearing
  per-frame flag write `sw v0,-0x3360(gp)` @`0x0023d8d4`).
- v1 force ignore-global (`0x0023D648`→li v0,1) = soft-lock. v2 NOP activation (`0x0023D6B4`) = stall.
- Blaming `enemies_random scope=per_level` for the fire — FALSE ALARM (just needed more NPC talks).

## Docs added

- `docs/lab/ANALYSIS-why-v3-works.md` — the definitive disassembly of the input-gate.
- `docs/lab/ANALYSIS-invis-door02-fire-barrier.md` — what removes the fire and what gates it.
- `docs/FINDINGS-TUTORIAL-2026-09-29.md` — the full investigation narrative.
- Lab probes under `docs/lab/` (all read-only, no game data): tutorial text/prose/strings, render
  disasm, process disasm, draw callers, two-draws verify, door-pin verify, drop-quantity probe.

## Shipping recipe (play-verified as CHAOS2)

`tools/builds/build_chaos.py` → `skip_intro` + `skip_tutorial` + enemy/gear/xp/drop/door stack.
Hand to Joshua with the honest note: "at the burning village, talk to the first NPC 2-3 times for
the fire to drop — not a soft-lock."

## Open / next

- The 2-3-talk quirk could be removed with a conditional auto-advance (let the dialogue step persist
  until `part2b`), but it's playable as-is — deferred, documented.
- Selective boot-movie skip (skip some `.pss` logos but not others) was discussed; needs the user to
  confirm the on-screen movie order before targeting individual call sites. Not started.

---

# Session progress — 2026-09-30

The boss-rush / gauntlet investigation, two new transforms, and an honest Tested/Experimental UI.

## Headline

Spent the session trying to build a **boss rush / gauntlet** (walk into rooms of fightable bosses,
chained exit-to-exit). After many play-tests it is **proven not achievable** in the data and is
marked BLOCKED with an instruction-level write-up. Along the way, shipped two real features
(`gold_max`, door-remap `scope`), recovered the boss→level mapping, and reworked the desktop UI to
split modes into **Tested** vs **Experimental (untested)** tabs with a **Summoner 2 — TBD** marker.

## Shipped and working (verified)

| Thing | What | Verified |
|---|---|---|
| `gold_max` transform | maxes every gold CONTAINER pickup (`+Give N`+`Messagebox "Gold"`) to its field width (999/99/9). Gold is container-only; enemies cannot drop gold; 1000 doesn't fit. | 17 pickups, dry-run verified |
| `door_destination_remap` `scope` option | `interior` (default/safe) / `overworld` / `all` — randomize transitions by group | verified across the 3 scopes |
| `tested_chaos` mode | the play-verified recipe: no tutorial + 1HP + random loot + maxed gold + boosted XP | play-verified (CHAOS2) |
| recovered boss→level map | each boss's level = its VPP member filename (TABLES.VPP TOC), not inline text | verified (`probe_boss_member.py`) |
| guard fix | `check-no-game-data.py` no longer false-flags large text/source files | guard clean |

## BLOCKED this session (marked `buildable: False` in the UI)

- **Boss Rush / Boss Rooms / Boss Gauntlet** — a boss-rush is not achievable: bosses are
  hidden/scripted set-pieces, NOT placement-registered enemies, so placing them faults the engine
  name-lookup (`0x72616863` "char" TLB crash); the levels that own them have only scene-critical
  NPCs; cross-level remapped doors render mid-story levels black. Full proof:
  `docs/BOSS-RUSH-INVESTIGATION.md` + `docs/BOSS-ROOMS-DESIGN.md`.
- **Roguelike** — stacks eleven unverified changes; blocked pending validation.

## The hard rules learned (do NOT relearn — see BOSS-RUSH-INVESTIGATION.md)

1. `$Character` / door-dest swaps are EQUAL-LENGTH only. Space-padding corrupts the record →
   `0x72616863` ("char") TLB freeze.
2. Only place a creature the level ALREADY loads as an active `+Monster` placement. Hidden/`+Boss`
   creatures aren't placement-registered → crash; unloaded models → black screen / load hang.
3. Don't overwrite or unlink scene-critical NPCs (name referenced elsewhere) → script freeze.
4. Remapped-door chaining renders fine for self-initializing levels; mid-story levels (sewerboss)
   render black; `endgame` is not a door target (no start slot).
5. Gold is container-only (max 999); enemies cannot drop gold. `+Drop` is item+chance, no quantity.

## UI change — honesty about what's tested

- New `tested` flag on modes (`rando_core.py`), surfaced through `cli.py --list`, read by
  `Models.cs` (`ModeInfo.Tested`).
- Desktop (`MainForm.cs`): the mode dropdown is now under a **TabControl** —
  **Tested** (play-verified: `vanilla_no_tutorial`, `tested_chaos`), **Experimental (untested)**
  (everything else; builds but not play-verified), and a disabled **Summoner 2 — TBD** tab.
- `docs/TESTING-HELP-WANTED.md` added (+ README pointer): what's verified, what needs testing, what's
  blocked, Summoner-2 TBD, and how to report a play-test result.

## Verification

cli `--list` emits `tested: [vanilla_no_tutorial, tested_chaos]`; desktop C# builds 0 errors/0
warnings; game-data guard clean (240 tracked files).

## Open / next

- Move Experimental modes to Tested as play-tests come back (`TESTING-HELP-WANTED.md` is the ask).
- Open leads from the boss work: a masad enemy-arena (swap non-story NPCs → active masad hostiles —
  needs the "which placements actually spawn" question answered) and a high-level-item-drop
  transform (143 enemy `+Drop` records; force chance 100 + equal-length high-tier swap). Both
  documented in `BOSS-RUSH-INVESTIGATION.md`.
- Summoner 2 (SLUS-20448): not started; UI marker is a placeholder only.
