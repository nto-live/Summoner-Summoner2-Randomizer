# Requirements Document

## Introduction

This feature delivers four independent, individually-modifiable randomizer options for the Summoner (USA) randomizer, each wired into the desktop WinForms UI, plus a default editable seed carrying the `nto_live` marker. The goal is a working state where the user launches the desktop application, enables all four options, builds one ISO, and tests it in-game.

Three of the four options produce working in-game effects today: randomized doors (existing `door_destination_remap` transform), randomized chests (existing `chest_items` transform), and a new size-preserving enemy-HP transform that sets every hostile creature's HP fields to a user-chosen value. The fourth option, "no start movie" (existing `skip_intro` binary patch), is surfaced honestly as an independent toggle that is present but pending: it writes nothing and reports why, because resolving its Ghidra address is out of scope for this feature.

All engine edits are size-preserving and follow the declare-and-refuse discipline. Documentation is updated at the end of the task with honest status labels: newly built or changed features are labeled "built, unverified" rather than "verified in game."

## Glossary

- **Randomizer**: The Summoner (USA) randomization engine, implemented in `src/cli.py` and `src/rando_core.py`.
- **Desktop_UI**: The WinForms desktop application implemented in `desktop/SummonerRando.Desktop/MainForm.cs`, which builds its feature grid and Options panel dynamically from `cli.py --list`.
- **Transform**: A size-preserving engine operation registered in the `TRANSFORMS`, `TRANSFORM_INFO`, `OPTIONS`, and `OPTION_AWARE` registries in `src/rando_core.py`.
- **Enemy_HP_Transform**: The new standalone size-preserving transform that sets every hostile `#Character Info` HP field to a user-settable value, reusing `HP_FIELDS`, `_fit_int_to_width`, and `_set_hp_uniform`.
- **HP_Fields**: The two per-creature fields `$Max Hit Points` and `$Hit Points`, defined in `HP_FIELDS` in `src/rando_core.py`.
- **Binary_Patch**: A fixed-width instruction patch defined in `src/binary.py`; `apply_patches` refuses to write any patch whose `va` is unresolved or that carries a `blocked` reason.
- **Skip_Intro_Patch**: The existing `skip_intro` `Patch` in `src/binary.py`, currently blocked because its address is unresolved.
- **Options_Panel**: The dynamically-rendered portion of the Desktop_UI that displays per-transform option controls (for example, a NumericUpDown for an int option).
- **Seed**: The randomization seed string used by the Randomizer; a valid default seed for this feature has the form `NTO_LIVE_<suffix>`.
- **Seed_Field**: The editable seed text control `_txtSeed` in the Desktop_UI.
- **Source_ISO**: The input game image at `C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso`.

## Requirements

### Requirement 1: Enemy-HP transform sets a user-settable value

**User Story:** As a randomizer user, I want to set every hostile creature's HP to a value I choose, so that I can tune combat difficulty independently of other stats.

#### Acceptance Criteria

1. THE Enemy_HP_Transform SHALL be registered as a standalone size-preserving Transform in the `TRANSFORMS`, `TRANSFORM_INFO`, `OPTIONS`, and `OPTION_AWARE` registries in `src/rando_core.py`.
2. THE Enemy_HP_Transform SHALL expose an int option with a default value of 1, a minimum of 1, and a maximum of 999.
3. WHEN the Enemy_HP_Transform runs with a requested value, THE Enemy_HP_Transform SHALL write that value into each `$Max Hit Points` field and each `$Hit Points` field of every hostile `#Character Info` definition.
4. THE Enemy_HP_Transform SHALL write the requested value right-justified and space-padded within each field's own existing byte width.
5. IF the requested value has more digits than a given HP_Field can hold, THEN THE Enemy_HP_Transform SHALL write the all-nines maximum that fits that field's width and SHALL continue processing that creature.
6. THE Enemy_HP_Transform SHALL preserve the byte width of every field it modifies.
7. THE Enemy_HP_Transform SHALL modify only the HP_Fields and SHALL leave attack, damage, and level fields unchanged.
8. THE Enemy_HP_Transform SHALL reuse the existing `HP_FIELDS`, `_fit_int_to_width`, and `_set_hp_uniform` helpers in `src/rando_core.py`.
9. THE Enemy_HP_Transform SHALL be defined independently of the bundled `hp` option in `enemy_stats_random`.

### Requirement 2: Doors option toggleable in the UI

**User Story:** As a randomizer user, I want to enable door randomization and choose how doors are remapped, so that I control the entrance layout independently of other options.

#### Acceptance Criteria

1. THE Desktop_UI SHALL present the existing `door_destination_remap` Transform as an independently toggleable feature in the feature grid.
2. WHERE the `door_destination_remap` feature is enabled, THE Options_Panel SHALL expose its `how` option control.
3. WHEN the user enables the `door_destination_remap` feature and builds an ISO, THE Randomizer SHALL apply door randomization according to the selected `how` value.

### Requirement 3: Chests option toggleable in the UI

**User Story:** As a randomizer user, I want to enable chest randomization, so that chest contents are shuffled independently of other options.

#### Acceptance Criteria

1. THE Desktop_UI SHALL present the existing `chest_items` Transform as an independently toggleable feature in the feature grid.
2. WHERE the `chest_items` feature is enabled, THE Options_Panel SHALL expose its `how` option control.
3. WHEN the user enables the `chest_items` feature and builds an ISO, THE Randomizer SHALL apply chest randomization according to the selected `how` value.

### Requirement 4: Enemy-HP option toggleable in the UI

**User Story:** As a randomizer user, I want to enable the enemy-HP option and enter a value in the UI, so that I can set hostile HP without editing files.

#### Acceptance Criteria

1. THE Desktop_UI SHALL present the Enemy_HP_Transform as an independently toggleable feature in the feature grid.
2. WHERE the Enemy_HP_Transform feature is enabled, THE Options_Panel SHALL auto-render a NumericUpDown control for its int option.
3. THE NumericUpDown control for the Enemy_HP_Transform SHALL default to 1.
4. WHEN the user enables the Enemy_HP_Transform feature and builds an ISO, THE Randomizer SHALL apply the Enemy_HP_Transform using the value entered in the NumericUpDown control.

### Requirement 5: Binary-patch toggle surfaced independently in the UI

**User Story:** As a randomizer user, I want binary patches to appear as their own independent toggle, so that I can select them without them being tied to a mode.

#### Acceptance Criteria

1. THE Desktop_UI SHALL present the Skip_Intro_Patch as an independently toggleable feature, separate from the mode controls.
2. THE Desktop_UI SHALL render the Skip_Intro_Patch toggle without coupling it to the Transform feature grid entries.

### Requirement 6: No-start-movie honest pending behaviour

**User Story:** As a randomizer user, I want the no-start-movie toggle to be honest about its status, so that I understand it does nothing yet and why.

#### Acceptance Criteria

1. WHEN the user enables the Skip_Intro_Patch toggle and builds an ISO, THE Randomizer SHALL write no bytes for the Skip_Intro_Patch.
2. WHEN the Skip_Intro_Patch is enabled during a build, THE Randomizer SHALL report that the patch is blocked and state the reason.
3. WHILE the Skip_Intro_Patch remains blocked, THE Randomizer SHALL allow the build to complete and apply the other enabled options.

### Requirement 7: Seed default and edit behaviour

**User Story:** As a randomizer user, I want a default seed carrying the `nto_live` marker that I can edit or regenerate, so that every build is identifiable and reproducible on my terms.

#### Acceptance Criteria

1. WHEN the Randomizer generates a default seed via `cli.py --seeds`, THE Randomizer SHALL produce a seed of the form `NTO_LIVE_<suffix>` where `<suffix>` is a random uppercase alphanumeric string.
2. THE Randomizer SHALL produce a different seed on each generation.
3. THE Randomizer SHALL return the generated seed in uppercase.
4. WHEN the Desktop_UI loads, THE Desktop_UI SHALL populate the Seed_Field with a generated `NTO_LIVE_` seed obtained via `--seeds 1`.
5. THE Desktop_UI SHALL allow the user to edit the Seed_Field.
6. WHEN the user activates the "Random seed" button, THE Desktop_UI SHALL regenerate an `NTO_LIVE_` seed into the Seed_Field.
7. WHEN the user builds an ISO with a value in the Seed_Field, THE Randomizer SHALL use the Seed_Field value in place of the default seed.

### Requirement 8: Combined ISO buildability

**User Story:** As a randomizer user, I want to enable all four options and build one ISO from my source game image, so that I can test everything in a single run.

#### Acceptance Criteria

1. WHEN the user enables the door, chest, enemy-HP, and no-start-movie options and builds from the Source_ISO, THE Randomizer SHALL produce one output ISO.
2. THE Randomizer SHALL accept the Source_ISO path `C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso` including its embedded spaces.
3. THE output ISO SHALL contain the applied door, chest, and enemy-HP changes.
4. THE output ISO SHALL reflect the Skip_Intro_Patch as present-but-pending with no bytes written for it.
5. THE Randomizer SHALL keep every engine edit size-preserving and SHALL refuse rather than write any change that would alter file size.

### Requirement 9: Documentation updated with honest status labels

**User Story:** As a maintainer, I want the documentation updated with honest status labels, so that readers know which features are built-and-untested versus verified in game.

#### Acceptance Criteria

1. WHEN the implementation is complete, THE maintainer SHALL update `MODES.md`, `FEATURES.md`, `PLANNED.md`, and `RESEARCH-SKIP-INTRO.md`.
2. THE documentation SHALL label newly built or changed features as "built, unverified" rather than "verified in game."
3. THE documentation SHALL record the Skip_Intro_Patch as present-but-pending pending resolution of its Ghidra address.

## Non-Goals

1. Resolving the Skip_Intro_Patch Ghidra address is explicitly out of scope for this feature. The no-start-movie toggle remains present-but-pending and writes nothing until the address is resolved in later work.
