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
