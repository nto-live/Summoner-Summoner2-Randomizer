# Requirements Document

## Introduction

This feature brings the Summoner (PlayStation 2) randomizer up to a defined completion bar: every
option the owner requested for Summoner 1 that can be built size-preservingly is finished to the
project's full standard, and everything that genuinely cannot be built is documented as blocked
with a reason rather than half-shipped.

The randomizer engine core is Python (`src/`: `cli.py`, `rando_core.py`, `binary.py`,
`discover.py`, `build.py`). The desktop application is C# WinForms
(`desktop/SummonerRando.Desktop`) that wraps the frozen Python engine through a JSON-in / JSON-out
command-line contract. Every world edit operates on the reassembled `TABLES.VPP` text stream and
must never change the stream's byte length, because the archive entries are arbitrary slices of one
continuous stream and any byte shift corrupts a boundary.

Scope covers five build-now transforms and the modes that carry them:
`player_stats_random` and `enemy_stats_random` (stat shuffles), `rooms_shuffle` (within-level
anchor permutation), NPC Hunt mode (over shipped `spawn_shuffle` + `npc_character_shuffle`),
Boss Rush (needs a boss inventory and arena navpoint list first), and Item Hunt (goods moved out
of shops and quest rewards into containers). It also covers a documented Summoner 2 extension plan
without building the Summoner 2 (VPP v2) reader.

Out of scope, and to remain documented as blocked: Collectionthon, encounter-rate scaling,
character colours and models, level order, a true One Hour reachability mode, `music_replace`, and
anything that grows the archive.

## Glossary

- **Engine**: The Python randomizer core in `src/` that reads a Summoner ISO, applies transforms to
  the `TABLES.VPP` text stream, and writes a new ISO. Entry points: `cli.py`, `build.py`,
  `rando_core.py`.
- **Desktop_App**: The C# WinForms application in `desktop/SummonerRando.Desktop` that invokes the
  frozen Engine over the JSON CLI contract and presents modes, transforms, and options to the user.
- **Transform**: A single named, seed-driven edit registered in `rando_core.TRANSFORMS` that
  rewrites specific fields in the `TABLES.VPP` stream while preserving the stream's byte length.
- **Mode**: A named preset in `rando_core.MODES` that selects a set of Transforms and supplies their
  default option values.
- **Option**: A named parameter of a Transform, declared in `rando_core.OPTIONS`, with a type,
  default, and allowed values.
- **TABLES_VPP**: The continuous 6,771,975-byte Summoner 1 text stream, sliced into 527
  `0x800`-aligned archive entries, on which every world Transform operates.
- **Size_Preserving**: A property of a Transform whereby the output `TABLES.VPP` stream has exactly
  the same byte length as the input; a value is only ever rewritten inside its own field width.
- **Character_Info_Block**: A `#Character Info` block in the stream carrying a `$Team:` value and
  numeric stat fields (hit points, ability points, aggressiveness, attack radius, view and
  detection ranges, movement and turn rates). 160 such blocks exist: 80 friendly and 80 hostile.
- **Player_Stats**: The numeric fields inside `$Team: "friendly"` Character_Info_Blocks — the
  playable party's hit points, ability points, aggressiveness, ranges, and turn rates. Summoner has
  no Strength, Dexterity, or Intelligence fields in these blocks.
- **Enemy_Stats**: The numeric fields inside hostile Character_Info_Blocks.
- **Start_Position_Anchor**: A `$Start position: "<navpoint>"` field on a placement record that
  binds the placement to a navpoint within its level.
- **Boss_Placement**: A placement record carrying the `+Boss` marker.
- **Arena_Navpoint_List**: The set of navpoints inside a single chosen level to which Boss Rush
  re-points every Boss_Placement's Start_Position_Anchor.
- **Container_Yield**: The `+Messagebox:` item-name string in a block that also carries a `+Give:`
  amount; the item a container actually grants.
- **Boot_Verified**: A change confirmed to produce the intended bytes, remain Size_Preserving, and
  produce an ISO that boots on the emulator, without the specific in-game effect being observed.
- **Play_Verified**: A change whose in-game effect has been observed on the emulator.
- **Fully_Fleshed_Bar**: The completion standard for a new Transform: Size_Preserving, registered in
  `cli.py --list`, measured with edit and byte counts recorded in `FEATURES.md`, wired into at least
  one Mode with Options, and surfaced in the Desktop_App UI with a label and help text.
- **VPP_v2_Reader**: An unbuilt component that would parse Summoner 2's archive format; its absence
  blocks all Summoner 2 randomization.

## Requirements

### Requirement 1

**User Story:** As a randomizer user, I want the player-stats and enemy-stats shuffles finished to
the project's completion standard, so that I can shuffle party and enemy numbers from both the
command line and the desktop application with confidence they preserve file size.

#### Acceptance Criteria

1. THE Engine SHALL register `player_stats_random` and `enemy_stats_random` as Transforms visible in
   the `cli.py --list` output.
2. WHEN `player_stats_random` runs, THE Engine SHALL permute the numeric Player_Stats fields only
   among `$Team: "friendly"` Character_Info_Blocks.
3. WHEN `enemy_stats_random` runs, THE Engine SHALL permute the numeric Enemy_Stats fields only
   among hostile Character_Info_Blocks.
4. WHEN either stat Transform writes a value into a field, THE Engine SHALL keep the output
   `TABLES.VPP` stream byte length identical to the input stream byte length.
5. IF a value cannot be written into a target field without changing that field's width, THEN THE
   Engine SHALL leave that field unchanged and record the field as skipped in the Transform report.
6. THE Desktop_App SHALL present `player_stats_random` and `enemy_stats_random`, and their `style`
   Option, each with a label and help text.
7. THE Engine SHALL record the measured edit count and byte count for `player_stats_random` and
   `enemy_stats_random` in `FEATURES.md`.

### Requirement 2

**User Story:** As a randomizer user, I want a within-level room shuffle, so that a level is
furnished differently while every location stays reachable.

#### Acceptance Criteria

1. THE Engine SHALL register `rooms_shuffle` as a Transform visible in the `cli.py --list` output.
2. WHEN `rooms_shuffle` runs, THE Engine SHALL permute Start_Position_Anchors only among placements
   within the same level.
3. THE Engine SHALL leave level graph, door destinations, quest data, and navpoint definitions
   unchanged when `rooms_shuffle` runs.
4. WHEN `rooms_shuffle` assigns a Start_Position_Anchor to a placement, THE Engine SHALL assign only
   an anchor that already exists within that same level.
5. WHEN `rooms_shuffle` completes, THE Engine SHALL keep the output `TABLES.VPP` stream byte length
   identical to the input stream byte length.
6. THE Engine SHALL provide a Mode that selects `rooms_shuffle`, and THE Desktop_App SHALL present
   that Mode and the `rooms_shuffle` Transform with a label and help text.
7. THE Engine SHALL record the measured edit count and byte count for `rooms_shuffle` in
   `FEATURES.md`.

### Requirement 3

**User Story:** As a randomizer user, I want an NPC Hunt mode, so that NPCs are neither where I left
them nor who I expect.

#### Acceptance Criteria

1. THE Engine SHALL register an NPC Hunt Mode that selects the shipped `spawn_shuffle` and
   `npc_character_shuffle` Transforms.
2. WHEN the NPC Hunt Mode runs, THE Engine SHALL resolve the Mode's Option values into the request
   through `rando_core.mode_options`.
3. WHEN the NPC Hunt Mode completes, THE Engine SHALL keep the output `TABLES.VPP` stream byte
   length identical to the input stream byte length.
4. THE Desktop_App SHALL present the NPC Hunt Mode with a label and help text.
5. THE Engine SHALL record the NPC Hunt Mode's constituent Transforms and their measured edit counts
   in `FEATURES.md`.
6. WHERE cross-level NPC relocation is not implemented, THE Engine SHALL document cross-level NPC
   relocation as a blocked or designed extension with its reason recorded in `PLANNED.md`.

### Requirement 4

**User Story:** As a randomizer user, I want a Boss Rush mode, so that the bosses stand together in
one arena and can be fought in one place.

#### Acceptance Criteria

1. THE Engine SHALL produce a boss inventory listing every Boss_Placement identified by the `+Boss`
   marker in the `TABLES.VPP` stream.
2. THE Engine SHALL produce an Arena_Navpoint_List enumerating the navpoints of a single chosen
   arena level.
3. WHEN Boss Rush runs, THE Engine SHALL re-point every Boss_Placement's Start_Position_Anchor to a
   navpoint in the Arena_Navpoint_List.
4. WHEN Boss Rush re-points a Start_Position_Anchor, THE Engine SHALL write only a navpoint name that
   fits the existing field width, keeping the output `TABLES.VPP` stream byte length identical to the
   input stream byte length.
5. IF a Boss_Placement has no arena navpoint that fits its field width, THEN THE Engine SHALL leave
   that Boss_Placement unchanged and record it as skipped in the Transform report.
6. THE Engine SHALL register the Boss Rush Transform in `cli.py --list`, provide a Boss Rush Mode,
   and THE Desktop_App SHALL present the Mode with a label and help text.
7. THE Engine SHALL record the measured edit count and byte count for Boss Rush in `FEATURES.md`.

### Requirement 5

**User Story:** As a randomizer user, I want an Item Hunt option that moves goods out of shops and
quest rewards into containers, so that items must be found rather than bought.

#### Acceptance Criteria

1. THE Engine SHALL register the Item Hunt Transform in the `cli.py --list` output.
2. WHEN Item Hunt runs, THE Engine SHALL move goods from shop stock and quest rewards into
   Container_Yields.
3. WHEN Item Hunt writes an item name into a Container_Yield, THE Engine SHALL write only a name that
   fits the existing field width, keeping the output `TABLES.VPP` stream byte length identical to the
   input stream byte length.
4. IF a good has no Container_Yield of matching field width, THEN THE Engine SHALL leave that good in
   place and record it as skipped in the Transform report.
5. THE Engine SHALL provide an Item Hunt Mode that combines the shipped `item_scatter` Transform with
   the Item Hunt Transform, and THE Desktop_App SHALL present the Mode with a label and help text.
6. THE Engine SHALL record the measured edit count and byte count for Item Hunt in `FEATURES.md`.

### Requirement 6

**User Story:** As a randomizer maintainer, I want every new option surfaced consistently across the
engine and the desktop application, so that the command line, the app, and any harness agree on what
a mode does.

#### Acceptance Criteria

1. THE Engine SHALL declare each new Option in `rando_core.OPTIONS` with a type, a default value, and
   its allowed values.
2. WHEN a Mode that includes a dial Transform is selected, THE Engine SHALL set that dial's value
   through the Mode's Options rather than leaving it at a value that produces no edits.
3. WHEN a caller supplies an explicit Option value, THE Engine SHALL apply the explicit value over
   the Mode default through `rando_core.mode_options`.
4. THE Desktop_App SHALL render each new Transform and Option with a label and help text sourced from
   the Engine's registry.
5. WHEN the Desktop_App invokes the Engine, THE Desktop_App SHALL exchange requests and results over
   the JSON-in / JSON-out command-line contract.

### Requirement 7

**User Story:** As a randomizer maintainer, I want every edit to preserve file size and to refuse
rather than guess, so that no built ISO is corrupted and no field is silently invented.

#### Acceptance Criteria

1. THE Engine SHALL keep the output `TABLES.VPP` stream byte length identical to the input stream
   byte length for every Transform in scope.
2. IF applying a value would move a field boundary, THEN THE Engine SHALL refuse that individual edit
   and record it as skipped.
3. IF a Transform receives an unknown Option value, THEN THE Engine SHALL change nothing and record a
   note stating the value was unrecognised.
4. THE Engine SHALL exclude any Summoner game data from the distributed artifact.

### Requirement 8

**User Story:** As a randomizer maintainer, I want unimplemented features documented as blocked
rather than partly shipped, so that the catalogue states honestly what exists.

#### Acceptance Criteria

1. THE Engine SHALL document Collectionthon, encounter-rate scaling, character colours, character
   models, level order, a true One Hour mode, `music_replace`, and any archive-growing edit as
   blocked, each with a recorded reason, in `PLANNED.md`.
2. THE Engine SHALL exclude every blocked item from the shipped Mode and Transform registries.
3. WHERE a feature in scope is completed, THE Engine SHALL meet the Fully_Fleshed_Bar before the
   feature is marked done.

### Requirement 9

**User Story:** As a randomizer maintainer, I want verification status distinguished between boot and
play, so that claims about a build reflect what was actually observed.

#### Acceptance Criteria

1. WHEN THE Engine records a Transform's status in `FEATURES.md`, THE Engine SHALL label each
   Transform as Boot_Verified or Play_Verified according to what was observed.
2. WHERE an in-game effect has not been observed, THE Engine SHALL label the Transform as
   Boot_Verified and state that the in-game effect is unverified.
3. THE Engine SHALL treat in-game verification through the headless emulator harness as a separate
   manual step outside the scope of this feature's acceptance.

### Requirement 10

**User Story:** As a randomizer maintainer, I want a documented plan for extending options to
Summoner 2 without building the reader now, so that the path is recorded while Summoner 1 is
completed first.

#### Acceptance Criteria

1. THE Engine SHALL complete the Summoner 1 option set defined in this document before Summoner 2
   work begins.
2. THE Engine SHALL document a placeholder plan for extending the option set to Summoner 2 in the
   project documentation.
3. THE Engine SHALL document that Summoner 2 randomization is blocked on the absence of a
   VPP_v2_Reader, and SHALL NOT build the VPP_v2_Reader as part of this feature.
