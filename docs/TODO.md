# What's left — open work

Prioritised. Each item says what it is, why it's not done, and the concrete next step. Anything
"blocked" has its reason recorded so it is never half-shipped. See `SESSION-PROGRESS.md` for what
landed and `PLANNED.md` for the full backlog.

## 1. Play-verify the current CHAOS disc  — **NEXT, needs Joshua + emulator**

The disc `out/Summoner-CHAOS.iso` (seed `CHAOS1`) is build-verified and boots, but the latest
change (holding overworld doors) is only **boot-verified**, not play-verified.

- [ ] First boat transition reaches the overworld (no "Exit to Unknown" → title).
- [ ] An interior randomized door loads a wrong-but-valid level (proves interior remap works in game).
- [ ] Killing an enemy grants ~9999 XP and jumps levels (fast leveling).
- [ ] Enemies die in one hit; a killed enemy drops its item; equipped gear reads high attack/defence.

## 2. Widen door coverage: complete the `+Index` start-slot map  — **medium, engine-side**

`_level_start_slots()` only resolves ~21 of 51 levels because it segments the blob by loose "Level
file for X" / `$Level:` markers. ~44 doors are skipped as a result (can't prove the destination has
the arrival slot).

- Next step: build the slot map from the per-level `#Navpoints` blocks directly (each level's
  `$player<party>-<slot>` navpoints), keyed to the level name reliably. Recover the 44 skips.
- Acceptance: door remap count rises toward ~195 (218 minus the 23 held overworld) with every
  remap still passing the slot check.

## 3. Overworld / masad door transitions  — **BLOCKED (held), needs the crossing understood**

The overworld-hub doors bounce to the title even when every static check passes. Held via
`DOOR_SOURCE_EXCLUDE`. To actually randomize them we need to understand the overworld load path.

- Next step: watch a real overworld crossing (PINE + the door harness, `DOOR-REMAP.md` §2.8) to see
  what differs from an interior load — is it a separate `select_new_game`/worldmap entry, a missing
  destination worldmap node, or an `+Index` semantics difference on the hub?
- Until then: leave held. A stranded first transition is game-breaking.

## 4. Disable the opening tutorial  — **BLOCKED (mechanism found, not patched)**

Mechanism mapped in Ghidra (see `PLANNED.md` §3): fire-once `+Flag` gates via `flag_is_set`
(`0x001f10a8`) / `flag_set` (`0x001f11e8`); an `Ignore tutorial` debug command exists
(`0x0023da14`). No single proven safe switch.

- Best next step (safest): find where **new-game initialises the flag array** and pre-set the
  `masad_*_tutorial` flags to "done" — this uses the game's own skip path and won't hang.
- Do NOT patch the shared `flag_is_set`/`flag_set` (every quest/event flag routes through them).
- Must be play-verified; rushing risks the boot hang the cutscene neuter caused.

## 5. Story-intro auto-skip  — **designed, not built**

The narrated opening `$Cutscene` (`Game-Pre-Intro` / `Game-Intro`) can't be neutered (hangs the
boot) but IS button-skippable in game. A proper skip means finding the flag/state the skip button
sets and forcing it. Related to #4 (same flag machinery). Lower priority — it's a one-button annoyance.

## 6. UI polish  — **small**

- [ ] Confirm the new transforms and their option controls render correctly in the desktop app
      (they're wired and the app builds; a visual pass with `SummonerRando.Harness --dump-ui` or a
      real run would confirm sliders/toggles show).
- [ ] Decide whether `enemy_xp_random` vs `enemy_xp_set` and `enemy_drops_random` vs
      `enemy_drops_always` should be mutually-exclusive in a mode (set overrides shuffle).

## 7. Housekeeping

- [ ] Fold the new transforms into named **modes** if desired (e.g. a "Power Trip" mode:
      1-HP enemies + max gear + fast XP + guaranteed drops).
- [ ] Update `FEATURES.md` / `MODES.md` with the new transforms once play-verified.
- [ ] Regenerate the `inventory.py` fixture (still pre-fix) if door counts are to be audited there.

---

### Known-good state to return to

- Engine transforms: all size-preserving, build-verified.
- `skip_intro`: play-verified (THQ logo gone).
- Doors: interior remap works byte-wise; overworld held on purpose.
- Nothing game-data is tracked; `python tools/check-no-game-data.py` is clean.


---

## Feature inventory — everything we want, with status

Status key: **DONE** (built + at least build-verified) · **PLAY?** (built, needs in-game check) ·
**WIP** (partially done / has a known gap) · **BLOCKED** (reason recorded) · **WANT** (desired, not
started). This is the master list; the sections above are the active next steps.

### Enemies & combat
- [DONE/PLAY?] All enemies 1 HP — `enemy_hp_set` (value settable).
- [DONE/PLAY?] Max weapon attack — `weapon_attack_max`.
- [DONE/PLAY?] Buff armour — `armor_protect_max`.
- [DONE/PLAY?] Random XP per kill — `enemy_xp_random`.
- [DONE/PLAY?] Settable XP per kill / fast leveling — `enemy_xp_set`.
- [DONE] Enemy difficulty dial / stat shuffle / placement — `enemy_difficulty`, `enemy_stats_random`,
  `enemies_amount`, `enemies_none`, `enemies_swarm` (pre-existing).
- [DONE/PLAY?] Randomize which enemies appear — `enemies_random`, now with `scope` option:
  `per_level` (SAFE, default — swaps only within a level so models stay loaded) or `global`
  (experimental — the old behaviour that caused MISSING WORLD GRAPHICS when a swapped-in creature's
  model wasn't loaded for that level). Use per_level.
- [DONE/PLAY?] Lower enemy attack — `enemy_damage_set` (sets hostile `$Damage`, default 0). NOTE:
  Summoner enemies have NO defence stat in the tables (verified 0 `$Protection` fields on 80 hostile
  blocks), so "lower enemy defence" is not possible; lowering their damage is the soften lever.
- [WANT] Settable weapon/armour values (not just max) — expose a `value` like the max transforms but
  allow any number; trivial extension of the two gear transforms.
- [WANT] Randomize (not just max) gear stats — shuffle `$Damage`/`$Protection` among items.
- [WANT] Randomize enemy attack/damage as its own lever (distinct from difficulty scaling).

### Loot & economy
- [DONE/PLAY?] Random enemy drops (which item) — `enemy_drops_random`.
- [DONE/PLAY?] Guaranteed drops (max existing chance) — `enemy_drops_always`.
- [BLOCKED] Force a drop on enemies that have NONE — needs adding bytes (breaks size-preservation);
  would require a repack or slack. Documented limit.
- [DONE] Item scatter / chest contents / chest payouts / shop prices — `item_scatter`, `chest_items`,
  `chest_shuffle`, `shop_shuffle`, `shops_free/crazy/none` (pre-existing).
- [WANT] Settable drop-chance value (not just max) — mirror the gear `value` option.
- [WANT] Guaranteed-random-drop: give every enemy a random item at 100% — blocked by the "no +Drop
  to add" limit above; revisit if a repack path opens.

### Transitions / doors / world
- [WIP] Randomize interior door destinations — `door_destination_remap`, 151/218, quote + `+Index` +
  `+Script` handled.
- [WIP] Complete the `+Index` start-slot map to recover ~44 skipped doors (TODO §2).
- [BLOCKED] Overworld / masad transitions random — held; hub load path not understood (TODO §3).
- [WANT] Reachability guard — ensure a seed can't strand the player (needs a flag/graph solver;
  long-standing design item in `PLANNED.md`).
- [WANT] One-way / trap doors; entrance-style "insanity" — designed in `PLANNED.md`, gated on the guard.

### Intro / cinematics / tutorial
- [DONE/PLAY-VERIFIED] Skip the `.pss` logo movies — `skip_intro` binary patch (THQ confirmed gone).
- [BLOCKED] Skip the in-engine story cinematic — neutering hangs the boot; it's button-skippable.
  Auto-skip needs the skip-flag/state (TODO §5).
- [BLOCKED] Disable the opening tutorial — mechanism found, not patched (TODO §4). Best path: pre-set
  the masad tutorial flags at new-game init.

### Audio / cosmetic
- [DONE] Music+SFX shuffle — `music_shuffle`; music-only — `music_tracks_shuffle`; SFX — `sound_shuffle`.
- [DONE] Icons, VFX, camera, fog, materials, models, animations, NPC behaviour — pre-existing shuffles.
- [BLOCKED] New music / palette colour swaps / new models — undecoded formats (`.vmu`, `.peg`, `.mvf`).

### Progression / pacing / modes
- [DONE] XP scale / level cap / cutscene bypass / dialogue blank / instant fades — pre-existing.
- [DONE] endgame_gate (binary) — lower the ending threshold.
- [WANT] A "Power Trip" mode bundling 1-HP + max gear + fast XP + guaranteed drops (housekeeping §7).
- [WANT] Ring Hunt / permadeath / roguelike modes — exist; keep tuning.
- [BLOCKED] True "One Hour" mode / collectionthon — need a flag graph / a collection counter.

### Platform / infra
- [BLOCKED] Summoner 2 support (`SLUS-20448`) — the VPP v2 reader does not exist.
- [WANT] Named modes for the new transforms + `FEATURES.md`/`MODES.md` updates once play-verified.
- [WANT] Regenerate the `inventory.py` fixture (pre-fix; undercounts doors).
