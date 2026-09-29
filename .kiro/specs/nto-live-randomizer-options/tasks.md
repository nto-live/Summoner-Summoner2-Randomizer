# Implementation Plan: NTO Live Randomizer Options

## Overview

This plan wires four independent randomizer options into the engine and the WinForms desktop UI, plus a default editable `NTO_LIVE_` seed. It proceeds engine-first (Python, `src/`) so the new `enemy_hp_set` transform, the `--binary` flag, the seed change, and the blocked `skip_intro` patch exist before the C# UI is wired against them. Property tests (Python `hypothesis`, min 100 iterations, tagged `Feature: nto-live-randomizer-options, Property N: <text>`) validate the five correctness properties in the design; example/integration tests cover registration, real builds, and UI plumbing. Verification runs the Python tests, `dotnet build`, and a final combined build with `--verify --against`. Documentation is updated last with honest status labels.

All engine edits are size-preserving and follow declare-and-refuse. The Source ISO path contains spaces and must be quoted everywhere: `"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso"`.

**Out of scope / Non-Goal:** Resolving the `skip_intro` Ghidra address is explicitly NOT a task. The `skip_intro` toggle stays present-but-pending; `va`/`original`/`encode` are preserved so a later task can unblock it by removing the `blocked` reason.

## Tasks

- [x] 1. Engine: add the `enemy_hp_set` transform and register it
  - [x] 1.1 Implement `t_enemy_hp_set(blob, rng, value=1)` in `src/rando_core.py`
    - Add the function near the other HP helpers, reusing `HP_FIELDS`, `_fit_int_to_width`, `_set_hp_uniform`, and `_hostile_char_blocks`
    - Coerce with `v = max(1, int(value))`; on non-int, append a refusal note and return the blob unchanged
    - When no hostile `#Character Info` blocks exist, return the blob unchanged with an explanatory note
    - HP-only, size-preserving, per-field all-9s clamp (inherited from `_fit_int_to_width`), writes both `$Max Hit Points` and `$Hit Points`; `rng` accepted but unused; independent of `enemy_stats_random`
    - Return `(new_blob, Report("enemy_hp_set"))`
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x] 1.2 Register `enemy_hp_set` in the four registries in `src/rando_core.py`
    - `TRANSFORMS`: add `"enemy_hp_set": t_enemy_hp_set`
    - `TRANSFORM_INFO`: add the `("Set enemy HP", "...")` label/description tuple (in-game effect unverified)
    - `OPTIONS["enemy_hp_set"]`: add int option key `value` — `{"type": "int", "default": 1, "min": 1, "max": 999, "label": ..., "help": ...}`
    - `OPTION_AWARE`: add `"enemy_hp_set"`
    - _Requirements: 1.1, 1.2_

  - [x] 1.3 Write property test for uniform HP write, per-field clamp, width preserved
    - **Property 1: Uniform HP write, per-field clamp, width preserved**
    - Tag: `Feature: nto-live-randomizer-options, Property 1: Uniform HP write, per-field clamp, width preserved`
    - Include the synthetic hostile `#Character Info` blob generator (random HP field widths, `$Team:` hostile) described in the design; assert every HP field parses to `min(v, int("9"*width))`, each field keeps its byte width, and `len(output) == len(input)`
    - hypothesis, min 100 iterations, value in `[1, 999]`
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.8, 8.5**

  - [x] 1.4 Write property test that only HP fields change
    - **Property 2: Only HP fields change**
    - Tag: `Feature: nto-live-randomizer-options, Property 2: Only HP fields change`
    - Synthetic blob interleaves HP fields with non-HP numeric fields (`$Attack`, `+Level:`); assert every byte outside an HP value span is identical to input
    - hypothesis, min 100 iterations
    - **Validates: Requirements 1.7**

- [x] 2. Engine: rewrite seed generation to emit `NTO_LIVE_` seeds
  - [x] 2.1 Rewrite `cmd_seeds` in `src/cli.py`
    - Prefix each generated seed with `NTO_LIVE_`; `--seed-length` now controls the random uppercase-alnum SUFFIX length
    - Keep uppercase A-Z + digits alphabet (uppercase by construction); use `random.SystemRandom`
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 2.2 Write property test for seed format and casing
    - **Property 3: Seed format and casing**
    - Tag: `Feature: nto-live-randomizer-options, Property 3: Seed format and casing`
    - For any generation count and any suffix length `L >= 1`, every seed matches `^NTO_LIVE_[A-Z0-9]{L}$` and equals its own uppercase
    - hypothesis, min 100 iterations
    - **Validates: Requirements 7.1, 7.3**

  - [x] 2.3 Write property test that seeds are distinct per generation
    - **Property 4: Seeds are distinct per generation**
    - Tag: `Feature: nto-live-randomizer-options, Property 4: Seeds are distinct per generation`
    - For any batch of `N` seeds in one call with suffix length >= 6, all `N` seeds are distinct
    - hypothesis, min 100 iterations
    - **Validates: Requirements 7.2**

- [x] 3. Engine: expose binary patches independently of modes via `--binary`
  - [x] 3.1 Add repeatable `--binary <name>` flag and union it into `binary_spec` in `src/cli.py`
    - `main()`: add `ap.add_argument("--binary", action="append", default=[], ...)`
    - `_resolve`: accept `binary_names`, union with `MODES[mode]["binary"]`, de-dup by patch name
    - `cmd_build`: pass `a.binary` into `_resolve`; keep backward compatibility with mode-supplied binary specs
    - _Requirements: 5.1, 5.2_

- [x] 4. Engine: mark `skip_intro` as present-but-pending
  - [x] 4.1 Add a `blocked` reason to the `skip_intro` Patch in `src/binary.py`
    - Add `blocked="movie-start call site not yet accepted; present but pending (see docs/RESEARCH-SKIP-INTRO.md)"`
    - Leave `va`/`original`/`encode` intact so it can be unblocked later by deleting one line
    - Verify `apply_patches` refuses it (writes zero bytes, `applied: false` with BLOCKED note) and `describe()` emits the `blocked` reason; the build still completes
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 4.2 Write property test that a blocked binary patch never aborts the build
    - **Property 5: A blocked binary patch never aborts the build**
    - Tag: `Feature: nto-live-randomizer-options, Property 5: A blocked binary patch never aborts the build`
    - For any subset of transform options (doors, chests, enemy-HP) combined with the blocked `skip_intro`, the build completes, `skip_intro` reports `applied: false` with a reason and writes zero bytes, and the transform edits equal those of the same build without `skip_intro`
    - hypothesis, min 100 iterations (vary the transform subset / enemy-HP value)
    - **Validates: Requirements 6.1, 6.2, 6.3, 8.4**

- [x] 5. Checkpoint - engine registration and behaviour
  - Ensure all tests pass, ask the user if questions arise.
  - Confirm `python src\cli.py --list` shows `enemy_hp_set` under `transforms`, `info`, `options` (int `value` default 1/min 1/max 999), `option_aware`; and `skip_intro` in the `binary` catalogue with a `blocked` reason
  - _Requirements: 1.1, 1.2, 5.1, 6.2_

- [x] 6. Engine: example / integration tests
  - [x] 6.1 Registration-visible example test
    - Assert `--list` JSON exposes `enemy_hp_set` in all four registries and `skip_intro` carries `blocked`
    - _Requirements: 1.1, 1.2, 6.2_

  - [x] 6.2 Dry-run and combined-build integration tests on the Source ISO
    - Dry-run `enemy_hp_set` with `--options "{\"enemy_hp_set\": {\"value\": 200}}"` — expect non-zero edits and no size change
    - Combined build with doors + chests + enemy_hp_set + `--binary skip_intro` on the quoted Source ISO `"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso"` — expect one ISO, door/chest/HP edits present, `skip_intro` reported `applied: false` BLOCKED
    - `--verify --against` proving same byte length and changes confined to TABLES.VPP (`outside_tables == 0`)
    - `--seeds` shape: `--seeds 5 --seed-length 8` yields five distinct `NTO_LIVE_<8 uppercase-alnum>` strings
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 7.1_

- [x] 7. Desktop UI: enemy-HP grid categorization
  - [x] 7.1 Add `"enemy_hp_set"` to the Gameplay HashSet in `MainForm.cs`
    - Categorizes the new grid row as gameplay; the NumericUpDown auto-renders via the existing dynamic options path (`RebuildOptions`/`AddOptionRow`) — verify, no other control code needed
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 8. Desktop UI: models for binary patches
  - [x] 8.1 Extend `BinaryInfo` and `BuildResult` in `Models.cs`
    - `BinaryInfo`: add `Blocked` field; parse `Blocked = p.Value.Str("blocked") ?? ""` in `ListPayload.Parse`
    - `BuildResult`: add a `Binary` list of `BinaryPatchRow { Patch, Applied, Notes }`, parsed from the `"binary"` result array mirroring how `reports` is parsed
    - _Requirements: 5.1, 6.2_

- [x] 9. Desktop UI: independent binary-patch toggle section
  - [x] 9.1 Add the "Binary patches" section in `MainForm.cs`
    - Add `HashSet<string> _binarySelected` state and a `FlowLayoutPanel _binaryHost` inside a `GroupBox "Binary patches (executable)"`
    - Populate one CheckBox per `_list.Binary` entry on `--list` load (main and harness paths); `Text = info.Label`, tooltip = `info.Help`, `Tag = key`; store checked state in `_binarySelected`
    - Decouple from `_dgv` and `ApplyMode` (toggling a mode never touches these); render blocked patches with a "pending" hint (e.g. append " — pending")
    - _Requirements: 5.1, 5.2, 6.2_

- [x] 10. Desktop UI: carry binary selection into the build
  - [x] 10.1 Extend `EngineClient.BuildArgs` with a `binary` parameter in `EngineClient.cs`
    - Emit `--binary <name>` per selected patch
    - _Requirements: 5.1, 6.1_

  - [x] 10.2 Pass `_binarySelected` from `RunBuildAsync` in `MainForm.cs`
    - Wire `_binarySelected` into the `BuildArgs` call so an independent `skip_intro` toggle reaches the engine via `--binary skip_intro` under the default `custom` mode
    - _Requirements: 5.1, 6.1_

- [x] 11. Desktop UI: surface blocked patch in the Result panel
  - [x] 11.1 Show `skip_intro` present-but-pending in `HandleBuildResult` (`MainForm.cs`)
    - After the "Per feature" block, append a "Binary patches" block to `_txtResult` surfacing `skip_intro` as `applied: false` BLOCKED with its reason, for both dry-run and build
    - _Requirements: 6.1, 6.2, 6.3, 8.4_

- [x] 12. Desktop UI: confirm seed field first-load population
  - [x] 12.1 Confirm seed field needs no structural change in `MainForm.cs`
    - `_txtSeed` is already editable (`CharacterCasing.Upper`), populated via `--seeds 1`, and regenerated by the "Random seed" button; with the `cmd_seeds` change it now carries `NTO_LIVE_...`
    - Optionally ensure first-load populates an `NTO_LIVE_` seed if `_txtSeed` is empty
    - _Requirements: 7.4, 7.5, 7.6, 7.7_

- [x] 13. Checkpoint - desktop build
  - Ensure all tests pass, ask the user if questions arise.
  - Run `dotnet build desktop\SummonerRando.sln` from repo root `C:\temp\NTO_Live_Code\Summoner-Summoner2-Randomizer` and fix any build errors
  - _Requirements: 4.1, 5.1, 6.2_

- [x] 14. Final verification: combined build with all four options
  - [x] 14.1 Run Python engine tests and fix failures
    - Run the property tests (Properties 1-5) and example/integration tests
    - _Requirements: 1.3, 1.7, 6.3, 7.1, 7.2, 8.4_

  - [x] 14.2 Combined dry-run/build producing one ISO with all four options + `--verify --against`
    - Build one ISO with doors + chests + enemy_hp_set + `--binary skip_intro` (skip_intro pending) from the quoted Source ISO
    - Run `--verify --against` proving size-preserving and changes confined to TABLES.VPP (`outside_tables == 0`); confirm `skip_intro` reported `applied: false` BLOCKED
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 15. Documentation: update with honest status labels
  - [x] 15.1 Update `docs/MODES.md`, `docs/FEATURES.md`, `docs/PLANNED.md`, `docs/RESEARCH-SKIP-INTRO.md`
    - Label `enemy_hp_set`, the doors/chests UI wiring, and the `NTO_LIVE_` seed as "built, unverified" (never "verified in game")
    - Record `skip_intro` as present-but-pending pending resolution of its Ghidra address (Non-Goal 1)
    - _Requirements: 9.1, 9.2, 9.3_

## Notes

- Tasks marked with `*` are optional (property tests, example/integration tests) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirement sub-clauses for traceability.
- Property-test tasks (1.3, 1.4, 2.2, 2.3, 4.2) each map to exactly one design correctness property and are placed next to the code they validate to catch errors early.
- Checkpoints (5, 13) provide incremental validation at engine and desktop boundaries.
- Non-Goal: resolving the `skip_intro` Ghidra address is out of scope and is deliberately NOT a task.
- The Source ISO path contains spaces and must be quoted in every CLI invocation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "2.3", "4.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "6.1", "7.1", "8.1"] },
    { "id": 3, "tasks": ["6.2", "9.1", "10.1", "12.1"] },
    { "id": 4, "tasks": ["10.2", "11.1"] },
    { "id": 5, "tasks": ["14.1"] },
    { "id": 6, "tasks": ["14.2"] },
    { "id": 7, "tasks": ["15.1"] }
  ]
}
```
