# Statement of Work — Summoner Randomizer

*Owner: Joshua (`nto-live`). Written and maintained by Jeni. Last updated 2026-09-21.*

---

## 1. Objective

Build a **randomizer for Summoner** (PS2, Volition/THQ, 2000, SLUS-20074), and later **Summoner 2**
(PS2, 2002, SLUS20448). A randomizer reshuffles the game's own contents so that no two
playthroughs match — which items sit where, what a door connects to, who stands where, how hard
the world fights back — and, in this case, when the game ends.

**Nobody has done this for Summoner.** In twenty-five years the only community tool for the PS2
release is a widescreen patch. Everything here was worked out from a retail disc.

## 2. Deliverable

**A Windows desktop application that takes the user's own disc image and writes a new one.**

* WinForms, single window. No browser, no server, no localhost.
* ISO in → **ISO out**. Same byte length, same ISO9660 layout, same boot ELF; only the data region
  is rewritten. The result plays in any PS2 emulator, or burnt to a disc on real hardware.
* The seed is shown in the window title and in the seed box, so a run can be copied and shared.
* Packaged to run on a machine with **nothing installed**: one folder holding the app
  (self-contained .NET) and the engine frozen with PyInstaller (no Python). See
  `desktop/PACKAGING.md`.

**The application never runs the game, never looks for an emulator, and never touches a disc in
place.** What the user does with the ISO afterwards is their business.

## 3. Rules this project holds to (non-negotiable)

1. **No game data is distributed, hosted, mirrored or linked.** Seeds, patches and code only. The
   site and the app say "bring your own legally dumped disc" and nothing more.
2. **The verified ISOs and part files on the development machine are never wiped.**
3. **Every edit is size-preserving** until the archive-slack question is answered — the 527
   `TABLES.VPP` entries are arbitrary slices of one stream, so nothing may shift by a byte.
4. **Unimplemented features are listed as blocked, with the reason** — never half-shipped.
5. **Boot-verified is not play-verified.** Claims say which one they are.

## 4. Scope

### In scope

| Area | What it means |
|---|---|
| Text layer | the game's script language inside `TABLES.VPP`: doors, dialogue, spawns, triggers, items, shops, chests, pacing dials |
| Binary layer | the executable (`SLUS_200.74`): declare-and-refuse word patches, verified by read-back and by the emulator's own CRC |
| Doors | rewriting a trigger's `$Trigger:` destination name in place — the headline feature |
| Enemies | which creatures stand where, how many, and how hard they hit |
| Progression | XP rate, level caps, permadeath, and which event opens the endgame |
| Seeds | deterministic: same seed + mode + options ⇒ byte-identical ISO |
| Verification | headless emulator harness, live memory introspection, and an engine-side `--verify` |

### Out of scope (deliberately)

* Shipping or linking game data, emulator binaries, BIOS files, ISOs or disc images.
* Running the game for the user — the app's contract ends at the ISO.
* Summoner 2's data layer until the VPP v2 reader exists (it is detected and refused with a reason).
* Anything that changes the archive's size (see rule 3) until the slack question is settled.

## 5. Work completed, with evidence

| Piece | State | Evidence |
|---|---|---|
| VPP v1 decoded, both retail discs rebuilt byte-identical | done | `PROJECT.md` §3 |
| Text layer: 37 transforms, 29 modes | done | `MODES.md` |
| Binary layer (`binary.py`): one-word-at-a-time patches, refuse-on-mismatch, read-back | done | `COMPILED-CODE.md` §7 |
| **Doors solved**: destination is the inline `$Trigger:` name; 218-patch remap applied | done | `DOOR-REMAP.md` |
| **Door remap verified in game** (2026-09-21) | done | two discs differing by one rewritten destination load two different levels — `DOOR-REMAP.md` §4.5 |
| **Headless gameplay** (PCSX2, no display, no pad) | done | Software renderer required; Vulkan freezes the game silently — `COMPILED-CODE.md` §8 |
| **Enemies**: remove / randomise / swarm / difficulty dial | implemented; removal **verified in game** against a control | combined no-enemies + remapped-door disc: every visited level holds fewer living entities (Liangshan 100 → 17, sewer 65 → 12); `ENEMIES.md` §4 |
| End-user packaging (app + frozen engine, no Python) | done | `desktop/PACKAGING.md` §5 |
| Engine testing surface: `--verify`, `--report`, `--log`, `-v` | done | `--verify` proves "0 changed bytes outside TABLES.VPP" |

## 6. Work in progress

* **Honest door crossing** — the in-game proof currently forces the door's geometry gates. Make a
  genuinely walking player cross a door.
* **Enemy verification** for swarm and the difficulty dial (only "No Enemies" is proven in game).
* **Level-raise tool** — live XP/level writing for the party, plus an automatic preset.
* **In-game text/logging** — hook the game's own text renderer (`FUN_00133608`) so the app's test
  runs can show, and log, the level and room the player is in.

## 7. Blocked, with reasons

| Item | Blocked by |
|---|---|
| Encounter-rate scaling | the `#Resistances` block layout is not mapped |
| Character colours | `.peg` texture format undecoded |
| Item relocation | the blob's segmentation map (chunk names are unreliable) |
| Adding spawns / any edit that grows the archive | the archive-slack question (619 KB of unused space; needs a boot test) |
| Summoner 2 | VPP v2 reader not written |
| Creature stats for 38 of 80 monsters | their stat sheets live in the executable's `.data`, not the text layer |

## 8. Verification method

Everything is checked by booting it, not by assertion:

* **Headless PCSX2** with the Software renderer, a test-only pnach for input and observation
  hooks, and **PINE** for live read/write of the emulated console's memory.
* **Engine-side**: `python cli.py --verify <iso> [--against <src>]` — structural checks, and proof
  that every changed byte lies inside the archive region.
* **In-game**: level loads are read straight out of `Level_data.name`; entity counts are walked out
  of the game's own `Living_entity_list`.
* Every claim in the docs states which of these it rests on. Where nothing was verified, the doc
  says so.

## 9. Acceptance criteria for this phase

1. A user on a clean Windows machine can run the app, point it at their disc, pick a mode and a
   seed, and get a playable ISO. *(Packaged and verified except the clean-machine run.)*
2. Every shipped mode is size-preserving and reversible. *(Verified per transform.)*
3. Every mode is either verified in game or documented as unverified, with the reason.
4. No game data, emulator binary or third-party tool is distributed with the project.

## 10. Repository layout

| Path | What |
|---|---|
| `cli.py` | the engine, JSON in/out, drift-free and GUI-free |
| `rando_core.py` | transforms + modes |
| `binary.py` | executable patches |
| `discover.py` | disc identification |
| `desktop/` | the WinForms app, the engine wrapper, and the UI harness |
| `desktop/PACKAGING.md` | how the portable bundle is built |
| `PROJECT.md` | the project record: status, findings, roadmap |
| `DOOR-REMAP.md` | the door mechanism, the patch, the in-game proof |
| `ENEMIES.md` | the enemy model and the difficulty dial |
| `MODES.md` | every mode and option with measured edit counts |
| `COMPILED-CODE.md` | Ghidra/R5900 toolchain, the patcher, the headless harness |
| `RESEARCH-*.md` | techniques taken from other randomizers, entrance-logic survey |
| `TIMER-DESIGN.md` | timed runs (designed, deferred by request) |
| `RESUME.md` | where the work stands, in one screen |
| `PLANNED.md` | **the to-be-implemented log** — every decided-but-unbuilt item, with state, mechanism and acceptance |
| `FEATURES.md` | the measured catalogue: what exists, with edit counts and verification status |

## 11. Legal and ethical

This is a fan tool for a game people already own. It ships no game data, no BIOS, no emulator and
no disc images, and it has no download or sharing endpoint. It only ever reads a disc image the
user supplies and writes a new one beside it. Every technique here was derived from a legally
dumped retail disc for interoperability, in the same spirit as the widescreen patches the PS2
scene has published for years.

*License: GPL-3.0 (see `LICENSE`), matching the repository.*
