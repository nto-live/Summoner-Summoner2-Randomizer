# Boss Rush / Boss Gauntlet — full investigation log

A complete record of the attempt to build a "boss rush / gauntlet" (walk into rooms of fightable
bosses, chained exit-to-exit) for Summoner. Many approaches were tried and play-tested; this
captures what works, what crashes, and the instruction-level reasons, so none of it is re-derived.

Pairs with `docs/BOSS-ROOMS-DESIGN.md` (the design) and the probes in `docs/lab/`.

## What SHIPPED and works (verified)

- **`gold_max`** transform: sets every GOLD container pickup (`+Give N` + `+Messagebox "Gold"`) to
  the max its fixed-width field allows (999 / 99 / 9). Gold is a CONTAINER pickup, not an enemy
  drop — there is no enemy→gold mechanism in the data (verified). 1000 cannot fit any field.
- **`door_destination_remap` `scope` option**: `interior` (default/safe) / `overworld` / `all`.
- **`boss_rush`** (pre-existing): clusters a level's `+Boss` placements onto one navpoint in that
  same level. Does NOT activate them.
- **`skip_tutorial`** (the input-gate NOP), **`enemy_hp_set`**, **`enemy_xp_set`**, etc.

## The GOAL and why it is hard

Wanted: start → a room full of aggressive bosses → exit → next boss room → … A "gauntlet".

Three independent constraints, each learned from a crash, strangle every approach:

1. **Size-preserving.** Every edit must keep byte width. `$Character` names can only be swapped for
   an equal-or-shorter name; door destinations likewise. No records can be added.
2. **Model-safe.** A creature can only be placed in a level that already LOADS its model, or the
   level load HANGS / black-screens. (Observed: boss in masad = stuck LOADING bar; swapped creature
   with unloaded model = flicker then freeze.)
3. **Aggro / clean slots.** A creature inherits the NPC placement's `+Action` list. `+Hidden` /
   `"turn hostile" 0` / `"wait for go"` / `"show/hide" 0` keep it passive/invisible. Only "clean"
   placements aggro.

## Approaches tried, and how each failed (all play-tested)

| # | approach | result |
|---|---|---|
| A | `boss_gauntlet`: chain the real boss levels' exit doors | you walk into EMPTY rooms — bosses are hidden/trigger-gated (`+Hidden`, `+Trigger "pyrulstart"`, `"wait for go"`), not spawn-on-arrival. The scripted activation never fires out of sequence. |
| B | chain only levels whose bosses are LIVE on arrival | only masad + jadetemple qualify, and they can't legally door-link (jadetemple has 0 doors; name too long for masad's door). |
| C | force-activate bosses (strip `+Hidden`/`wait for go`) | per-boss script surgery; intro-cutscene dependencies; abandoned as too risky. |
| D | place activation TRIGGERS at the player start | triggers are `$Trigger` spline/area VOLUMES tied to level geometry (`.p3d`) + would be NEW records = adds bytes. Both forbidden. |
| E | `boss_rooms`: overwrite a level's NPC `$Character` with hostile bosses, chain exits | multiple failures, see below. |

### boss_rooms (E) — the detailed failure chain

1. **Padding `$Character` with spaces → FREEZE.** First build padded names (`"Orenian Scout "` +
   spaces). In-game: TLB-miss crash loop reading `addr=0x72616863` ("char") — the engine's
   name-lookup (`lb` at `pc=0x112ce0`, a stricmp-style scan) was handed TEXT as a pointer and
   walked off into the script stream. Of 1102 retail `$Character` names, exactly ONE has a trailing
   space, so padding is effectively illegal. **Rule: equal-length `$Character` swaps only.**
2. **masad load HANG.** Putting bosses in masad hung the load (black screen, full LOADING bar) —
   masad does not load boss models. **Rule: model-safe only (level must already load the creature).**
3. **Equal-length + model-safe collapses the roster.** With both rules, almost no slot qualifies:
   TempleInt owns 5 bosses (names 5–11) but its clean slots are wide (12–23) → 0 equal-length fits;
   it also loads ZERO hostile placements, so nothing model-safe fits either.
4. **TempleInt NPCs are all scene-critical.** All 30 clean slots have `$Name`s referenced 4–13×
   elsewhere (rites/dialogue/triggers). Renaming one (`Med High Priest`→Pyrul) froze on the priest
   dialogue scene. Unlinking them (`$npc`→`$zzz`, the `enemies_none` trick) ALSO froze — the engine
   iterates the placement list and faults on the dangling navpoint (`pc=0x152f38`, walking by 8).
5. **TempleInt boss placement = "char" fault even with few edits.** A minimal build (1 Pyrul + 10
   unlinks, 11 edits total) still froze on the masad→TempleInt transition with the `0x72616863`
   ("char") fault. Pyrul's definition is `+Hidden`/`+Boss` in TempleInt — it is NOT registered in
   the normal placement-creature table the name lookup searches, so a regular placement referencing
   "Pyrul" walks off the table → crash.

### Door-chain rendering

- masad→TempleInt door hop **renders TempleInt fully** (play-verified: temple interior loaded with
  priests) — so remapped-door chaining CAN load a level. Padding one `$Character` did NOT stop that
  render; the later freeze was the dialogue scene, not the door.
- `sewerboss` reached via a remapped door loaded **black** (geometry/lighting absent) — a mid-story
  level expects to be entered from `sewer` with state; cold entry renders black.
- `endgame` is NOT a valid door target: `DOOR_TARGET_EXCLUDE`, no start slots, zero existing doors
  to it. The ending is a scripted event (`endgame_gate` gamestage threshold), not a walkable level.

## The core wall (instruction-level proof)

Levels split into two kinds, neither usable:
- **Boss levels** — bosses are hidden/scripted, NOT placement-registered; placing them on normal
  slots crashes with the `0x72616863` ("char") name-lookup fault; their NPCs are all scene-critical.
- **Normal levels** — have disposable NPCs but do NOT load boss models; placing a boss crashes
  (unloaded model / black screen).

There is **no level** that both (a) loads a boss as a usable placement creature and (b) has
disposable, clean, equal-width NPC slots AND (c) chains via a door that renders. The game never
spawns bosses as normal enemies — they are always scripted set-pieces.

## Open leads (not yet resolved)

- **masad enemy arena**: swap masad's NON-story NPCs to masad's ACTIVE hostiles (Barbarian Fighter
  17 / Orenian Soldier 16 / Archer 14 / Scout 13), equal-length. Build `make_masad_barb.py` /
  `make_active_test.py`. REPORTED by Joshua: the barbs did NOT show (original enemies stayed) — the
  targeted slots may be `CS#` cutscene placements that don't spawn in normal play, or the swap did
  not apply to the visible crowd. NEEDS: identify which masad placements are the ones actually
  visible/spawned in normal play, and confirm an equal-length active-hostile swap on THOSE renders.
- **high-level item drops**: 143 enemy `+Drop` records exist with a chance value; forcing chance to
  100 (`enemy_drops_always`) + swapping the item to a high-tier one of equal length is feasible and
  NOT yet built as a dedicated transform.

## Hard rules for any future attempt (do NOT relearn)

1. `$Character` / door-dest swaps are EQUAL-LENGTH only. Space-padding corrupts the record →
   `0x72616863` ("char") TLB freeze.
2. Only place a creature the level ALREADY loads as an active placement (`+Monster`). Hidden/`+Boss`
   creatures are not placement-registered → "char" fault. Unloaded models → black screen / hang.
3. Do not overwrite or unlink scene-critical NPCs (name referenced elsewhere) → script freeze.
4. Remapped-door chaining renders fine for self-initializing levels; mid-story levels (sewerboss)
   render black; `endgame` is not a door target.
5. Gold is container-only (max 999); enemies cannot drop gold.

## Probes (all read-only, docs/lab/)

probe_boss_member / probe_boss_region / probe_boss_map / probe_level_blocks (boss→level via VPP
member TOC), probe_boss_classify (live vs gated), probe_gauntlet_feasible2 / probe_gauntlet_path /
probe_interior_chain / probe_live_chain / probe_temple_chain (door chaining), probe_npc_to_boss /
probe_clean_npc / probe_safe_slots / probe_templeint(_models) (slot classification), probe_aggro /
probe_activate_edits / probe_wait_for_go / probe_trigger_mechanism (activation), probe_gold(_widths)
/ probe_masad_loot / probe_drop_owners / probe_boss_drops / probe_drop_boost (loot), probe_fault_pc
(disassembly of the crash PCs), probe_endgame.
