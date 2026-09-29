# How the Summoner Randomizer Works — Architecture Outline

*Written 2026-09-28. A plain-language map of the whole system: what the pieces are, how a
disc flows through them, and where each responsibility lives. Grounded in the code as it
stands (`cli.py`, `build.py`, `rando_core.py`, `binary.py`, `discover.py`, the desktop app,
and `package-portable.ps1`), not on recollection. Where a claim is measured elsewhere it
points at the source doc rather than repeating the number.*

---

## 1. The one-paragraph version

You supply your own Summoner PS2 disc image. The tool identifies it, reads the game's script
archive out of it, rewrites chosen fields in that script stream (and, for a couple of features,
patches the executable), and writes a brand-new playable ISO — same size as the original, with
a reproducible **seed** printed so the exact result can be recreated or shared. No game data is
ever distributed; the only thing that leaves the tool is a seed and (optionally) a patch.

---

## 2. The layers, top to bottom

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop app (WinForms, .NET 8)   desktop\SummonerRando.*     │  what a user sees
│    - ISO in, mode + seed, ISO out; shows the seed             │
│    - finds a PCSX2 emulator so a built disc can be launched   │
└───────────────┬─────────────────────────────────────────────┘
                │ runs as a subprocess, talks JSON
┌───────────────▼─────────────────────────────────────────────┐
│  Engine CLI            cli.py        (JSON in / JSON out)     │  the contract
│    --list --identify --build --dry-run --verify --seeds       │
└───────────────┬─────────────────────────────────────────────┘
                │ imports
┌───────────────▼─────────────────────────────────────────────┐
│  discover.py   identify a disc, locate its VPP archives       │  "what is this disc?"
│  rando_core.py the transforms, the modes, the ISO pipeline    │  "change the data layer"
│  binary.py     declare-and-refuse patches to SLUS_200.74      │  "change the code layer"
└───────────────────────────────────────────────────────────────┘
```

Two independent editing layers sit at the bottom:

- **The text/data layer** (`rando_core.py`) edits the plain-text script stream inside
  `TABLES.VPP`. This is where almost everything lives — enemies, shops, chests, doors,
  dialogue, and (the current work) creature stats.
- **The binary layer** (`binary.py`) edits the game executable `SLUS_200.74` a machine word at
  a time. Only a couple of features need it (e.g. `endgame_gate`). It is deliberately tiny and
  paranoid.

Both layers obey the same non-negotiable rule: **every edit is size-preserving.** Nothing is
inserted or deleted; a value is only ever rewritten inside its own fixed-width field. The reason
is structural and is explained in §5.

---

## 3. The data flow of one build

```
your ISO
  │
  ▼  discover.identify()            volume id + archive fingerprint → is this Summoner 1?
  │                                 (Summoner 2 is detected and refused, with a reason)
  ▼  rando_core.randomize_iso()
  │     1. read the VPP table of contents, find TABLES.VPP
  │     2. reassemble its entries into one continuous script stream (the "blob")
  │     3. run each selected transform over the blob, in order
  │        - each returns a modified blob + a Report (fields changed, bytes, skips)
  │     4. write each entry's slice back into its own byte range in a copy of the ISO
  │     5. (if the mode asks) apply binary.py patches to SLUS_200.74 in that copy
  │     6. hash the result; assert the size is identical to the source
  ▼
new ISO  +  a JSON result (edits, bytes changed, seed, sha256, per-transform reports)
```

The **seed** drives every shuffle through a seeded RNG, so *same disc + same mode + same
options + same seed → byte-identical ISO*. That reproducibility is what makes seed sharing and
racing possible.

`--dry-run` runs steps 1–3 and reports the counts **without writing** the 1.2 GB file — the fast
way to measure a transform.

`--verify` re-opens a built disc and checks it is a valid image; with `--against <source>` it
proves the discipline directly: same byte length, and every changed byte inside `TABLES.VPP`,
nothing outside it.

---

## 4. What each file is responsible for

| File | Responsibility |
|---|---|
| `desktop\SummonerRando.Desktop` | the WinForms window: pick disc/mode/seed, show the seed, Build, Play |
| `desktop\SummonerRando.Engine` | C# side that launches the engine as a subprocess and parses its JSON |
| `desktop\SummonerRando.Harness` | the same plumbing driven from a console, no GUI — for testing |
| `cli.py` | the engine's JSON interface; argument parsing, progress on stderr, one JSON object on stdout |
| `build.py` | a terminal-first builder over the same pipeline (`--list`, `--matrix`, `--dry-run`) |
| `discover.py` | disc identification and VPP archive location; the `identify()` / `find_tables()` API |
| `rando_core.py` | the transform registry, the mode presets, the option specs, and `randomize_iso` / `dry_run_iso` |
| `binary.py` | the ELF patch class: `find_elf`, `va_to_iso_offset`, `apply_patches`, declare-and-refuse + read-back |
| `package-portable.ps1` | freezes `cli.py` with PyInstaller and publishes the app into one portable folder |
| `tools\check-no-game-data.py` | the guard that must pass before every push — no game data in the repo |
| `docs\lab\` | reverse-engineering probes and headless-emulator scripts (reference `F:\rando\...`) |
| `docs\evidence\` | captured proof (logs, verification JSON) |

### How the pieces find each other

- `cli.py` and `build.py` each insert **their own directory** onto `sys.path` and then
  `import discover`, `import rando_core`, `import binary`. So the three engine modules must sit
  **beside** whichever script imports them.
- `binary.py` is imported defensively (`try/except ImportError`) — the engine still runs if it
  is absent, it just reports no binary patches.
- The desktop app locates the engine script at runtime (`SummonerRando.Engine`), and
  `package-portable.ps1` names `cli.py` explicitly. **These two are the coupling points a code
  reorganization must update** — moving the Python files without fixing them breaks the app and
  the portable build.

---

## 5. The one constraint that shapes everything

`TABLES.VPP` is **one continuous ~6.77 MB text stream** sliced into 527 archive entries, and
most of those slices cut through the middle of a line. The chunk names are therefore unreliable
labels, and — critically — **the slice boundaries must not move**. If a transform changed the
length of any field, it would shift every byte after it and corrupt the stream.

So every transform is **length-neutral**:

- numeric values are swapped only between fields of the same digit width;
- names are swapped only with same-length names;
- a door destination is rewritten as `new + '"' + spaces(len(old) - len(new))` — exactly the
  same byte count in and out.

A run that would move a boundary is **refused**, not forced. This is why features are described
as "size-preserving" everywhere, and why some values are simply unshuffleable (no same-length
partner exists). Full treatment: `MODES.md` → "The constraint everything obeys", and
`FEATURES.md` §0.

---

## 6. Transforms, modes, and options

- A **transform** is one focused edit over the blob (e.g. `shops_free`, `enemies_amount`,
  `door_destination_remap`). It is registered in `rando_core.py` and returns a **Report** so the
  exact number of fields it changed — and anything it refused — is always measured, never
  guessed.
- A **mode** is a named preset: a list of transforms plus its own default option values, wired
  so the CLI, the app, and any harness all agree on what a mode does. A mode that uses a dial
  **must** set a value (a rule the project learned the hard way — see `FEATURES.md` §0).
- **Options** are the dials on option-bearing transforms (e.g. `enemy_difficulty.level`,
  `xp_scale.percent`, `door_destination_remap.how`). Mode values are defaults; explicit
  `--options` override them.

The authoritative, measured catalogue of all of these is `FEATURES.md` (generated from the
engine's own registry, then measured); `MODES.md` is the player-facing reading of the modes.

---

## 7. The two verification layers, and the honesty rule

Two very different senses of "it works":

- **Byte-verified** — the engine changed exactly the bytes it declared, the image is the same
  size, and `--verify --against` shows nothing changed outside `TABLES.VPP`. This the engine can
  prove by itself.
- **Boot-verified vs play-verified** — a headless PCSX2 rig (documented in `COMPILED-CODE.md`
  §8) can boot a disc, and with the Software renderer + PINE can even read the running game's
  state. "Boots" is not "plays"; "the right level loaded" is not "a player walked through the
  door". Every claim in the docs says which one it is.

The project rule, stated plainly and repeatedly: **boot-verified is not play-verified**, and any
feature that cannot be verified in game says so rather than implying more.

---

## 8. What is deliberately not here

- No game data, ISO, blob, BIOS, or screenshot of game text lives in the repo. The archive is
  extracted at runtime from the user's own disc; the guard `tools\check-no-game-data.py` enforces
  this before every push.
- The end user still needs a PS2 emulator (or real hardware) and their own BIOS to *play* a
  built disc; the app finds PCSX2 but ships none.
- Summoner 2 is detected but not yet editable — the VPP v2 reader is unwritten (`PLANNED.md`).

---

## 9. Where to read next

| You want to understand… | Read |
|---|---|
| The whole project status and roadmap | `PROJECT.md` |
| The one-screen state and the next action | `RESUME.md` |
| Every feature with measured edit counts | `FEATURES.md` |
| Every mode as a player sees it | `MODES.md` |
| The decided-but-unbuilt queue | `PLANNED.md` |
| The door mechanism and its proof | `DOOR-REMAP.md` |
| The Ghidra toolchain, the binary patcher, the headless rig | `COMPILED-CODE.md` |
| How door/room randomization is solved genre-wide | `RESEARCH-ENTRANCE-LOGIC.md` |
