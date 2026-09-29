# Design Document
# Design Document

## Overview

This design wires four independent randomizer options into the WinForms desktop app and gives the engine a default seed carrying the `nto_live` marker. Three options produce working in-game effects: doors (`door_destination_remap`, existing), chests (`chest_items`, existing), and a **new standalone size-preserving enemy-HP transform** (`enemy_hp_set`). The fourth, "no start movie" (`skip_intro`), is surfaced honestly as an independent toggle that is present-but-pending — it writes nothing and reports why.

The design is grounded in the real codebase:

- Engine: `src/rando_core.py`, `src/cli.py`, `src/binary.py`
- Desktop: `desktop/SummonerRando.Desktop/MainForm.cs`, `desktop/SummonerRando.Engine/EngineClient.cs`, `desktop/SummonerRando.Engine/Models.cs`
- Solution: `desktop/SummonerRando.sln`
- Repo root: `C:\temp\NTO_Live_Code\Summoner-Summoner2-Randomizer`
- Source ISO (path contains spaces, must be quoted everywhere): `C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso`

Everything the engine writes stays size-preserving and follows the declare-and-refuse discipline (`_apply_transforms` refuses any step that changes blob length — `rando_core.py` ~line 3005).

### A discrepancy that this design resolves

The task brief states "skip_intro stays BLOCKED in binary.py (no change to the patch)." The actual code disagrees: the `skip_intro` `Patch` in `src/binary.py` (~lines 191–204) currently has a **resolved** `va=0x0022A2C8`, `original=0x0C089FA2`, an `encode` that no-ops the `jal`, and **no `blocked` reason**. As written today `apply_patches` (`binary.py` ~lines 218–260) would actually *write* that patch, because the only things that make it refuse are `p.blocked` or `p.va is None` (~line 234).

The requirements (Req 6.1, 6.2; Req 9.3; Non-Goal 1) are explicit that `skip_intro` must write nothing and report a reason until its Ghidra address work is accepted. To satisfy the requirements honestly, the design **adds a `blocked` reason string to the `skip_intro` Patch** so `apply_patches` refuses it. This is the smallest change that makes "present-but-pending" true. It is called out here rather than silently skipped because it contradicts the brief's "no change to the patch" note; the `va`/`original`/`encode` fields are left intact so the patch can be unblocked later by deleting one line.

## Architecture

```
Desktop (C#, WinForms)                         Engine (Python, stdlib only)
┌───────────────────────────┐                 ┌─────────────────────────────────────┐
│ MainForm.cs                │                 │ cli.py                              │
│  feature grid  (_dgv)      │  --list  ─────► │  cmd_list()  -> transforms/info/    │
│  Options panel (_optHost)  │ ◄─── JSON       │              options/binary catalogue│
│  binary toggles (NEW)      │                 │                                     │
│  seed field    (_txtSeed)  │  --seeds 1 ───► │  cmd_seeds() -> NTO_LIVE_<suffix>   │
│  Result / Pending panels   │  --build ─────► │  cmd_build() -> _resolve + randomize │
│                            │ ◄─── JSON       │                                     │
│ EngineClient.BuildArgs()   │                 │ rando_core.py                       │
│  (+ --binary NEW)          │                 │  TRANSFORMS / TRANSFORM_INFO /      │
│ Models.cs                  │                 │  OPTIONS / OPTION_AWARE             │
│  ListPayload / BinaryInfo  │                 │  t_enemy_hp_set (NEW)               │
│  BuildResult (+binary NEW) │                 │  randomize_iso / dry_run_iso        │
└───────────────────────────┘                 │ binary.py                           │
                                               │  PATCHES[skip_intro] (+blocked NEW) │
                                               │  apply_patches / describe()         │
                                               └─────────────────────────────────────┘
```

The desktop app already builds its feature grid and Options panel **dynamically** from `cli.py --list` (`MainForm.PopulateFeatures` ~line 442; `RebuildOptions` ~line 526; `AddOptionRow` ~line 574). Registering a new transform in the engine is therefore enough for it to appear in the grid and, if option-aware with an int option, auto-render a `NumericUpDown`. The only genuinely new UI surface is the **independent binary-patch toggle**, because binary patches are not transforms and are not in the grid today.

## Components and Interfaces

### 1. Engine: the new `enemy_hp_set` transform (`src/rando_core.py`)

#### 1.1 Transform convention (confirmed from existing transforms)

Transforms are plain functions `(blob, rng, **options) -> (new_blob, Report)`. The runner `_apply_transforms` (~lines 2984–3010) does:

```python
kw = dict(options.get(name) or {}) if name in OPTION_AWARE else {}
kw = {k: v for k, v in kw.items() if v is not None}
new_blob, rep = fn(blob, rng, **kw) if kw else fn(blob, rng)
if len(new_blob) != len(blob):
    # REFUSED: size changed ...
```

So options flow as keyword arguments, and only transforms listed in `OPTION_AWARE` receive them. Two concrete examples of the pattern:

- `t_chest_items(blob, rng, how="shuffle")` — `rando_core.py` line 865. Registered in `TRANSFORMS` (~line 2551), `TRANSFORM_INFO` (~line 2424, label "Chest contents"), `OPTIONS["chest_items"]` (~lines 2173–2181, a `choice` option `how`), and `OPTION_AWARE` (~line 2170).
- `t_enemy_difficulty(blob, rng, level="normal", level_shift=0)` — `rando_core.py` line 1537. Registered in `TRANSFORMS`, `TRANSFORM_INFO`, `OPTIONS["enemy_difficulty"]` (~lines 2228–2244, which shows the `int` option shape: `{"type": "int", "default": 0, "min": -20, "max": 20, "label": ..., "help": ...}`), and `OPTION_AWARE`.
- `xp_scale` / `levelcap_set` (`OPTIONS` ~lines 2182–2196) show an int option with `min`/`max` (`5`/`999`) — the exact schema shape the desktop reads to build a `NumericUpDown`.

#### 1.2 Reused helpers (confirmed ~lines 1722–1818)

- `HP_FIELDS` (line 1722): the two regexes `(\$Max Hit Points\s*:\s*)(\d+)` and `(\$Hit Points\s*:\s*)(\d+)`.
- `_fit_int_to_width(value, width)` (line 1747): clamps to the field's all-nines maximum (`int("9"*width)`) and right-justifies with leading spaces. Size-preserving by construction — returns exactly `width` bytes.
- `_set_hp_uniform(blob, blocks, value, rep)` (line 1770): iterates each block, each `HP_FIELDS` regex, rewrites `group(2)` in place using `_fit_int_to_width`, counts hits into `rep.changed`, appends a note. Returns a new `bytes`.
- `_hostile_char_blocks(blob)` (line 1247): `(start, end)` for every `#Character Info` block whose `$Team:` is hostile.
- `Report` dataclass (line 219): `transform`, `changed`, `notes` (`.as_dict()` is what the runner records).

#### 1.3 New transform function

```python
def t_enemy_hp_set(blob, rng, value=1):
    """Set EVERY hostile creature's HP fields to a single user-chosen value.

    Standalone size-preserving lever, independent of enemy_stats_random's bundled
    `hp` option. Writes the same number into each $Max Hit Points and $Hit Points
    of every hostile #Character Info block, right-justified inside the field's own
    byte width (all-9s clamp if the value will not fit). HP only — attack, damage
    and level fields are never touched. rng is unused: the value is deterministic.
    """
    rep = Report("enemy_hp_set")
    try:
        v = max(1, int(value))
    except (TypeError, ValueError):
        rep.notes.append(f"unusable value {value!r} - refused, nothing changed")
        return blob, rep
    blocks = _hostile_char_blocks(blob)
    if not blocks:
        rep.notes.append("no hostile #Character Info blocks found - nothing changed")
        return blob, rep
    out = _set_hp_uniform(blob, blocks, v, rep)
    rep.notes.insert(0, f"{len(blocks)} hostile creature definitions, hp set to {v}")
    rep.notes.append("HP only; attack/damage/level untouched")
    rep.notes.append("size-preserving; each HP written inside its own field width")
    return out, rep
```

Notes on the signature choice:
- `value=1` matches the transform convention (keyword option with a default) and the option default in Req 1.2.
- `rng` is accepted but unused, exactly like a deterministic transform must, because the runner always calls `fn(blob, rng, **kw)`.
- Reuses `_hostile_char_blocks`, `HP_FIELDS` (via `_set_hp_uniform`), and `_fit_int_to_width` (via `_set_hp_uniform`) — satisfying Req 1.8. The per-field all-9s clamp (Req 1.5) and width preservation (Req 1.6) are inherited from `_fit_int_to_width` unchanged. Writing both HP fields (Req 1.3) is inherited from `_set_hp_uniform` iterating both `HP_FIELDS` regexes.
- HP-only (Req 1.7): `_set_hp_uniform` only ever rewrites `HP_FIELDS` matches, so attack/damage/level bytes are never in a modified span.

#### 1.4 Registration (four registries, exact edits)

- **`TRANSFORMS`** (~line 2531): add `"enemy_hp_set": t_enemy_hp_set,` alongside `enemy_stats_random`/`player_stats_random`.
- **`TRANSFORM_INFO`** (~line 2304): add a `(label, description)` tuple:
  ```python
  "enemy_hp_set": (
      "Set enemy HP",
      "Sets every hostile creature's $Max Hit Points and $Hit Points to one value "
      "you choose, padded into each field's own width (all-9s clamp if it will not "
      "fit). HP only - attack, damage and level are left alone. Independent of the "
      "enemy_stats_random 'hp' option. Size-preserving. In-game effect unverified.",
  ),
  ```
- **`OPTIONS`** (~line 2171): add the int option. **Option key name: `value`** (matches the transform kwarg):
  ```python
  "enemy_hp_set": {
      "value": {
          "type": "int", "default": 1, "min": 1, "max": 999,
          "label": "Enemy HP",
          "help": "Every hostile creature is set to this many hit points. Clamped "
                  "per field to the largest value that fits its width, so the disc "
                  "never changes size.",
      },
  },
  ```
- **`OPTION_AWARE`** (~line 2166): add `"enemy_hp_set"` to the set.

#### 1.5 How the value flows from `--options` JSON into the transform

`cmd_build` (`cli.py` line 290) reads `--options` as JSON and merges it over mode defaults via `rc.mode_options(...)` (~line 305). The desktop sends, for a value of 200:

```json
{"enemy_hp_set": {"value": 200}}
```

`_apply_transforms` sees `enemy_hp_set` in `OPTION_AWARE`, extracts `{"value": 200}`, drops any `None`, and calls `t_enemy_hp_set(blob, rng, value=200)`. The same path feeds `dry_run_iso`'s per-transform impact loop (`rando_core.py` ~lines 3046–3050).

Because `enemy_hp_set` is its own key, it is completely independent of `enemy_stats_random`'s `hp` sub-option (Req 1.9): selecting one does not require or affect the other.

### 2. Engine: seed generation (`src/cli.py cmd_seeds`)

#### 2.1 Current code (lines 270–275)

```python
def cmd_seeds(n: int, length: int = 6) -> int:
    alpha = string.ascii_uppercase + string.digits
    rng = random.SystemRandom()
    _emit({"seeds": ["".join(rng.choice(alpha) for _ in range(length))
                     for _ in range(max(1, n))]})
    return 0
```

`--seed-length` defaults to 6 (`main()` ~line 338) and is passed as `length` (~line 373).

#### 2.2 New code shape

Prefix every generated seed with `NTO_LIVE_` and keep `--seed-length` semantics as the **length of the random suffix** (not the total). The alphabet is already uppercase alphanumeric, so the result is uppercase by construction (Req 7.3).

```python
def cmd_seeds(n: int, length: int = 6) -> int:
    # --seed-length now controls the random SUFFIX length; the NTO_LIVE_ marker
    # is fixed. Alphabet is uppercase A-Z + 0-9, so every seed is uppercase.
    alpha = string.ascii_uppercase + string.digits
    rng = random.SystemRandom()
    width = max(1, length)
    def one() -> str:
        return "NTO_LIVE_" + "".join(rng.choice(alpha) for _ in range(width))
    _emit({"seeds": [one() for _ in range(max(1, n))]})
    return 0
```

- Req 7.1: seeds match `^NTO_LIVE_[A-Z0-9]+$`.
- Req 7.2: `SystemRandom` per-character draw makes each generation different (collision improbable for a 6+ char suffix).
- Req 7.3: uppercase-only alphabet; the marker `NTO_LIVE_` is already uppercase.
- `--seed-length` semantics defined: **suffix length**. Total seed length is `len("NTO_LIVE_") + length` = `9 + length`.

The build seed default (`--seed default="SUMMONER"`, `cli.py` ~line 343) is unchanged; that only affects `--build` when no seed is passed. The desktop always passes an explicit `--seed` from `_txtSeed`, and populates `_txtSeed` from `--seeds 1`, so builds carry the `NTO_LIVE_` seed (Req 7.4, 7.7).

### 3. Engine: exposing binary patches independently of modes (`src/cli.py`, `src/binary.py`)

#### 3.1 How binary patches flow today

- The catalogue is exposed by `binary.describe()` (`binary.py` ~line 263), surfaced under the `"binary"` key of `cmd_list()` (`cli.py` line 148).
- Selection currently happens **only via modes**: `_resolve` (`cli.py` line 278) returns `binary = rc.MODES.get(mode, {}).get("binary") or []` (line 286). `cmd_build` passes that as `binary_spec` into `randomize_iso`/`dry_run_iso` (lines 301, 317, 324).
- `MODES["skip_intro"]` (`rando_core.py` ~line 2891) carries `"binary": [["skip_intro", {}]]`. That is the only route to request `skip_intro` today — i.e. it is coupled to a mode.
- `apply_patches` (`binary.py` ~lines 218–260) applies a list of `(name, params)` pairs; a patch with `p.blocked` or `p.va is None` returns `applied: false` with a `BLOCKED` note and writes nothing (~lines 234–240). `dry_run_iso` mirrors this read-only (`rando_core.py` ~lines 3058–3090).

#### 3.2 Decoupling: a new `--binary` CLI flag

To let an independent UI toggle request `skip_intro` **without selecting a mode**, add a repeatable `--binary <name>` flag that appends `(name, {})` to `binary_spec` on top of whatever the mode contributes.

- `main()` (`cli.py` ~line 340): add
  ```python
  ap.add_argument("--binary", action="append", default=[],
                  help="binary patch name (repeatable); independent of --mode")
  ```
- `_resolve` (line 278): accept the new list and union it with the mode's binary spec, de-duplicating by patch name:
  ```python
  def _resolve(mode, transforms, include, exclude, binary_names=None):
      tf = list(rc.MODES[mode]["transforms"]) if mode in rc.MODES else list(transforms or [])
      for t in list(exclude or []):
          if t in tf: tf.remove(t)
      for t in list(include or []):
          if t not in tf: tf.append(t)
      binary = list(rc.MODES.get(mode, {}).get("binary") or [])
      have = {n for n, _ in binary}
      for name in (binary_names or []):
          if name not in have:
              binary.append([name, {}])
              have.add(name)
      return tf, binary
  ```
- `cmd_build` (line 301): `tf, binary_spec = _resolve(a.mode, a.transforms, a.include, a.exclude, a.binary)`.

This is additive and backward-compatible: modes that already ship a binary spec keep working, and the `custom` mode (the desktop's default when no preset is chosen) now gains a way to carry `skip_intro`.

#### 3.3 `skip_intro` present-but-pending (`src/binary.py`)

Add a `blocked` reason to the `skip_intro` Patch (~lines 194–204) so `apply_patches` refuses it (Req 6.1, 6.2; Non-Goal 1). Leave `va`/`original`/`encode` intact for later unblocking:

```python
"skip_intro": Patch(
    name="skip_intro",
    va=0x0022A2C8,
    original=0x0C089FA2,
    encode=lambda p: 0x00000000,
    label="Skip the startup movie",
    help="...unchanged...",
    blocked="movie-start call site not yet accepted; present but pending "
            "(see docs/RESEARCH-SKIP-INTRO.md)",
),
```

Effect: `describe()` now emits `"blocked": "..."` for `skip_intro` (the `if p.blocked` branch, `binary.py` ~line 273), and both `apply_patches` and the dry-run path report `applied: false` with the `BLOCKED` note and write zero bytes. The build still completes and other options still apply (Req 6.3), because the binary layer runs after the transforms and never raises for a blocked patch.

### 4. Desktop UI (`desktop/SummonerRando.Desktop/MainForm.cs`)

#### 4.1 Enemy-HP feature auto-renders (Req 4.1–4.4) — confirmed

The grid is built from `_list.Transforms` in `PopulateFeatures` (~line 442), one checkbox row per transform, tagged with the transform name (~line 451). The Options panel is built in `RebuildOptions` (~line 526): for each checked `OPTION_AWARE` transform with a non-empty schema it renders a `GroupBox`, and `AddOptionRow` (~line 574) renders a `NumericUpDown` for `type == "int"` with `Minimum = spec.Min ?? 0` (~line 629) and the schema default.

So once `enemy_hp_set` is registered as an int-option, option-aware transform, it **auto-appears** as a grid row and, when checked, auto-renders a `NumericUpDown` defaulting to 1 (Req 4.2, 4.3). No new control code is needed. The build already sends its value: `BuildOptionsJson(checkedSet)` (~line 652) walks checked transforms and emits `{"enemy_hp_set": {"value": N}}` (Req 4.4).

**One small UI change:** the grid categorizes each row as `"gameplay"` or `"visual"` via the `Gameplay` `HashSet` (~lines 24–31) — `kind = Gameplay.Contains(name) ? "gameplay" : "visual"` (~line 448). To categorize the new transform correctly, add `"enemy_hp_set"` to that set. This is presentation only; it does not affect behaviour.

#### 4.2 Independent binary-patch toggle (Req 5.1, 5.2)

The `--list` `"binary"` payload is already parsed into `ListPayload.Binary` (`Models.cs` ~lines 214–225), a `Dictionary<string, BinaryInfo>` with `Label`, `Help`, `Va`, `Expects`. Today it is only summarised in the blocked/pending pane (`_txtPending`). The design adds a dedicated **"Binary patches" section** rendered from `_list.Binary`, decoupled from both the transform grid and the mode combo:

- Add a small container (e.g. a `FlowLayoutPanel` `_binaryHost` inside a `GroupBox "Binary patches (executable)"`) beneath the feature grid or in the Options column.
- On `--list` load (end of the load path near `PopulateFeatures`, ~line 442, and in the harness path ~line 785), populate one `CheckBox` per `_list.Binary` entry: `Text = info.Label`, tooltip = `info.Help`, `Tag = key`. Store checked state in a `HashSet<string> _binarySelected`.
- These checkboxes are **not** rows in `_dgv` and are **not** driven by `ApplyMode` (~line 457), satisfying Req 5.1/5.2 (independent of modes and of the transform grid). Toggling a mode never checks or unchecks them.
- Extend `BinaryInfo` (`Models.cs` ~line 81) with a `Blocked` field and parse it: `Blocked = p.Value.Str("blocked") ?? ""` in `ListPayload.Parse` (~line 218). Render blocked patches with a greyed hint (e.g. append " — pending" to the label) so the UI is honest before the build even runs.

#### 4.3 Carrying the toggle into the build (`EngineClient.BuildArgs`)

`RunBuildAsync` (~line 866) assembles the arg vector via `EngineClient.BuildArgs(iso, modeKey, seed, outPath, dryRun, include, exclude, optionsJson)` (~line 911). Extend `BuildArgs` (`EngineClient.cs` ~line 80) with a `binary` parameter and emit `--binary <name>` per selected patch:

```csharp
public static List<string> BuildArgs(
    string iso, string mode, string seed, string outPath, bool dryRun,
    IEnumerable<string>? include = null, IEnumerable<string>? exclude = null,
    string? optionsJson = null, IEnumerable<string>? binary = null)
{
    var args = new List<string> { "--build", iso, "--mode", mode, "--seed", seed, "--out", outPath };
    if (dryRun) args.Add("--dry-run");
    if (exclude is not null) foreach (var t in exclude) { args.Add("--exclude"); args.Add(t); }
    if (include is not null) foreach (var t in include) { args.Add("--include"); args.Add(t); }
    if (!string.IsNullOrWhiteSpace(optionsJson) && optionsJson != "{}") { args.Add("--options"); args.Add(optionsJson!); }
    if (binary is not null) foreach (var b in binary) { args.Add("--binary"); args.Add(b); }
    return args;
}
```

In `RunBuildAsync`, pass `_binarySelected` as the new argument. Because the desktop's default mode is `custom` (no bundled binary spec), an independent `skip_intro` toggle now reaches the engine purely through `--binary skip_intro` — decoupled from modes.

#### 4.4 Honest pending in the Result / Pending panels (Req 6.1–6.3)

`randomize_iso`/`dry_run_iso` already return the per-patch report array under the `"binary"` key with `applied: false` and the `BLOCKED` note. Today `BuildResult.Parse` (`Models.cs` ~line 315) does **not** read that key, so the desktop never shows it. The design:

- Add a `Binary` list to `BuildResult` (a small `record`/class: `Patch`, `Applied`, `Notes`) and parse the `"binary"` array in `BuildResult.Parse` mirroring how `reports` is parsed (~lines 320–336).
- In `HandleBuildResult` (`MainForm.cs` ~line 945), after the "Per feature" block (~line 990), append a "Binary patches" block to `_txtResult`:
  ```
  Binary patches:
    skip_intro            not applied — BLOCKED: movie-start call site not yet accepted...
  ```
  This makes the pending state visible right in the Result panel for both dry-run and build. The existing `_txtPending` pane (fed by `BuildPendingText`, ~line 1080) continues to advertise blocked features from `--list` before any build.

#### 4.5 Seed field (Req 7.4–7.7) — confirmed, no structural change

- `_txtSeed` is already editable (`Multiline` off, `CharacterCasing = CharacterCasing.Upper`, ~lines 194–197) and populated via `--seeds 1` (`RandomizeSeedAsync` ~line 679 → `_txtSeed.Text = seeds[0]`, ~line 686). With the `cmd_seeds` change it now carries `NTO_LIVE_...` automatically (Req 7.4, 7.6).
- The "Random seed" button (`_btnSeed`, wired ~line 112) calls the same path (Req 7.6).
- The build passes `_txtSeed.Text.Trim()` as `--seed` (~lines 881, 911), so an edited seed is used verbatim (Req 7.5, 7.7).
- No UI change needed beyond the engine's `cmd_seeds` change. One optional nicety: on first load, if `_txtSeed` is empty, trigger a `--seeds 1` fetch so the field starts populated with an `NTO_LIVE_` seed.

## Data Models

### Engine (Python)

- **`Report`** (`rando_core.py` line 219): `{transform: str, changed: int, refused: bool, notes: list[str]}` via `.as_dict()`. The new transform emits one.
- **`OPTIONS["enemy_hp_set"]["value"]`**: `{"type": "int", "default": 1, "min": 1, "max": 999, "label": str, "help": str}`.
- **`binary_spec`**: `list[[name: str, params: dict]]`, e.g. `[["skip_intro", {}]]`. Now populated from `MODES[mode]["binary"]` unioned with `--binary` names.
- **`describe()` entry** (`binary.py` ~line 263): `{label, help, va, expects, params, blocked?}` — `blocked` present for `skip_intro` after this change.
- **`--seeds` output**: `{"seeds": ["NTO_LIVE_<suffix>", ...]}`.

### Desktop (C#, `Models.cs`)

- **`BinaryInfo`** (~line 81): add `public string Blocked { get; init; } = "";` and parse it in `ListPayload.Parse`.
- **`BuildResult`** (~line 300): add `public IReadOnlyList<BinaryPatchRow> Binary { get; init; } = Array.Empty<BinaryPatchRow>();` where `BinaryPatchRow { string Patch; bool Applied; IReadOnlyList<string> Notes; }`, parsed from the `"binary"` array.
- **`MainForm` state**: add `HashSet<string> _binarySelected` and a `FlowLayoutPanel _binaryHost`.

## Error Handling

- **Value out of range / non-numeric** (`t_enemy_hp_set`): coerced via `max(1, int(value))`; a non-int refuses with a note and returns the blob unchanged. The UI `NumericUpDown` already constrains to `[min, max]` from the schema, so out-of-range values cannot originate in the UI.
- **Over-wide value per field** (Req 1.5): `_fit_int_to_width` clamps to `int("9"*width)` — never grows, never raises.
- **No hostile blocks**: transform returns unchanged with an explanatory note (no crash).
- **Size growth**: `_apply_transforms` refuses any step whose output length differs (`rando_core.py` ~line 3005). `enemy_hp_set` is size-preserving by construction, so it never trips this, but the guard remains the backstop (Req 8.5).
- **Blocked binary patch**: `apply_patches` returns `applied: false` with a `BLOCKED` note and writes nothing; it never raises, so the build completes (Req 6.1–6.3).
- **Source ISO path with spaces**: the desktop passes the ISO via `ProcessStartInfo.ArgumentList` (`EngineClient.cs` ~line 125), which handles spaces without manual quoting. For manual CLI use the path must be wrapped in double quotes, e.g. `--build "C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso"` (Req 8.2).
- **Unknown `--binary` name**: `apply_patches` reports `{"applied": false, "notes": ["unknown patch"]}` (`binary.py` ~line 225) — surfaced honestly, no crash.

## Testing Strategy

**Dual approach.** Property tests (Python `hypothesis`, min 100 iterations each) cover the universal write/seed behaviour of the new engine code; example/integration tests cover registration, the real build, and UI plumbing. Property tests are tagged `Feature: nto-live-randomizer-options, Property N: <text>`.

**Where PBT applies:** the `enemy_hp_set` write logic and seed generation are pure, input-varying functions — ideal for PBT. UI rendering (grid, NumericUpDown, toggles) and the blocked-patch report are example/integration territory, not PBT.

**Synthetic blob generator** for HP properties: build byte strings containing random hostile `#Character Info` blocks with `$Team:` hostile, random `$Max Hit Points` / `$Hit Points` fields of varying widths, interleaved with non-HP numeric fields (`$Attack`, `+Level:`) to prove they are untouched.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — a formal statement about what the system should do. Properties bridge human-readable specs and machine-verifiable guarantees.*

### Property 1: Uniform HP write, per-field clamp, width preserved

*For any* blob of hostile `#Character Info` blocks and *any* requested value `v` in `[1, 999]`, after `t_enemy_hp_set(blob, rng, value=v)` every `$Max Hit Points` and `$Hit Points` field parses to `min(v, int("9" * field_width))`, each field keeps its original byte width, and `len(output) == len(input)`.

**Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.8, 8.5**

### Property 2: Only HP fields change

*For any* blob containing hostile HP fields interleaved with non-HP numeric fields (attack, damage, level), after `t_enemy_hp_set` every byte outside a `$Max Hit Points` / `$Hit Points` value span is identical to the input.

**Validates: Requirements 1.7**

### Property 3: Seed format and casing

*For any* number of generations and *any* suffix length `L >= 1`, every seed produced by `cmd_seeds` matches `^NTO_LIVE_[A-Z0-9]{L}$` and equals its own uppercase.

**Validates: Requirements 7.1, 7.3**

### Property 4: Seeds are distinct per generation

*For any* batch of `N` seeds generated in one `cmd_seeds` call with a suffix length of at least 6, all `N` seeds are distinct.

**Validates: Requirements 7.2**

### Property 5: A blocked binary patch never aborts the build

*For any* subset of the transform options (doors, chests, enemy-HP) combined with the blocked `skip_intro` patch, the build completes, `skip_intro` reports `applied: false` with a reason and writes zero bytes, and the transform edits equal those of the same build without `skip_intro`.

**Validates: Requirements 6.1, 6.2, 6.3, 8.4**

## Verification Approach

All commands run from the repo root `C:\temp\NTO_Live_Code\Summoner-Summoner2-Randomizer`. The Source ISO path contains spaces and is quoted every time.

1. **Registration + option visible** — `python src\cli.py --list` shows `enemy_hp_set` under `transforms`, `info`, `options` (int `value` default 1/min 1/max 999), and `option_aware`; and the `"binary"` catalogue shows `skip_intro` with a `"blocked"` reason.
2. **Dry run of the new transform** —
   `python src\cli.py --build "C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso" --mode custom --include enemy_hp_set --options "{\"enemy_hp_set\": {\"value\": 200}}" --dry-run` — expect non-zero `enemy_hp_set` edits and no size change.
3. **Combined build (all four options)** —
   `python src\cli.py --build "C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso" --mode custom --include door_destination_remap --include chest_items --include enemy_hp_set --binary skip_intro --options "{\"enemy_hp_set\": {\"value\": 50}}" --seed NTO_LIVE_TEST01 --out work\out\combined.iso` — expect one ISO, door/chest/HP edits present, and `skip_intro` reported `applied: false` BLOCKED (Req 8.1–8.4).
4. **Size-preserving proof** —
   `python src\cli.py --verify work\out\combined.iso --against "C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso"` — expect "same byte length" and "changes confined to TABLES.VPP" (`outside_tables == 0`). Note: an *applied* `skip_intro` would touch the ELF (outside TABLES.VPP); because it is blocked, nothing is written there, so the confinement check stays green.
5. **Seed shape** — `python src\cli.py --seeds 5 --seed-length 8` — expect five distinct `NTO_LIVE_<8 uppercase-alnum>` strings.
6. **Desktop builds** — `dotnet build desktop\SummonerRando.sln -c Release` — expect a clean build. Manual smoke: launch the app, confirm `enemy_hp_set` appears in the grid with a default-1 NumericUpDown, the `skip_intro` toggle appears as an independent (non-mode, non-grid) checkbox, the seed field is pre-filled with `NTO_LIVE_`, and a build surfaces `skip_intro` as pending in the Result panel.
7. **Automated tests** — run the property tests (Properties 1–5) and the registration example tests; run any existing harness (`desktop/SummonerRando.Harness`) that exercises `HarnessApplySeed` / the `--list`-driven population path.

## Documentation Updates (Req 9)

At the end of implementation, update `docs/MODES.md`, `docs/FEATURES.md`, `docs/PLANNED.md`, and `docs/RESEARCH-SKIP-INTRO.md`: label `enemy_hp_set`, the doors/chests UI wiring, and the `NTO_LIVE_` seed as **"built, unverified"** rather than "verified in game," and record `skip_intro` as **present-but-pending** pending acceptance of its Ghidra address (Non-Goal 1).

## Non-Goals

Resolving the `skip_intro` Ghidra address is out of scope. The toggle remains present-but-pending and writes nothing. The `va`/`original`/`encode` fields in the `skip_intro` Patch are preserved so a future task can unblock it by removing the `blocked` reason.
