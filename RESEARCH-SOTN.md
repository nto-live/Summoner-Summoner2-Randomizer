# Research — Techniques Consumed From the SotN Randomizer

*Written 2026-09-20. Sources are public; no game data is copied from any of them.*

The Castlevania: Symphony of the Night randomizer is the closest thing to what we are
building — a PS1/PS2-era console game, a large community, a mature multi-year codebase, and
a set of problems that map almost one-to-one onto ours. It is worth reading carefully
rather than skimming, because **two of its design decisions would save us real work**.
This document records what we took, what we will take later, and what we deliberately reject.

## 1. The sources

| Project | What it is | Why it matters to us |
|---|---|---|
| `sotnrando/sotnrando` (`3snowp7im/SotN-Randomizer`) | **the randomizer itself** — Node/JS, patch-the-disc tool | the main source. PPF mode, presets, seed URLs |
| `TalicZealot/Sotn-Utilities` | speedrun / romhacking / TAS research tools | links to the whole ecosystem; decomp reference |
| `TalicZealot/SotnRandoTools` | in-emulator tracker + autosplitter over **SotnApi** | emulator-side **memory reading** — our observation problem |
| `Xeeynamo/sotn-decomp` | full decompilation of the game | precedent: our Ghidra/R5900 work is the same play |
| `KernelEquinox/SotN-Editor`, `MainMemory/SotNCastleEditor` | data / castle editors | prior art for editing level data |
| `MottZilla/SotN_Integrated_Rando` + the **Area Randomizer** | separate tool that randomizes **red doors** | the doors problem, already attacked by someone else |
| `sotnrando/SotNRandomizerLauncher` | bundles emulator + timer + patcher + updater | packaging/UX model |
| `sotn.io`, `sotn.dev` | the web randomizer + documentation hub | preset authoring docs, seed URLs |

## 2. Adopted now

### 2.1 PPF patch output instead of a full disc image — the big one
SotN's CLI writes a **PPF patch file** when you omit the input image:

```shell
$ node randomize -o rando.ppf     # patch file, not a 1.2 GB image
```

For us this is valuable twice over:

- **It removes the last trace of game data from what we hand out.** We already ship no ISOs,
  but a seed that is a *few hundred kilobytes of diffs* is unambiguously not game data. It is
  the cleanest possible expression of the project's hard rule, and it makes seeds trivially
  shareable and comparable.
- **It makes the iteration loop fast.** Our `iterate.ps1` currently takes ~80 s per cycle
  almost entirely because `randomize_iso` writes a fresh 1.2 GB copy. A diff-based build would
  cut the patch step to seconds. For a loop we intend to run dozens of times on doors, that
  is the difference between workable and painful.

Planned as `cli.py --patch-only <out.patch>`, with the format recorded in the patch file
header so a future build can apply it. **Not yet built** — listed in `PROJECT.md` §6.

### 2.2 Seed URLs and a race mode
SotN seeds are shareable as a URL: `https://sotn.io/?myseed`, and pasting one back in
reproduces the seed exactly. `--race` turns on a fixed verbosity so racers see the same
information. We already have deterministic seeds (same seed → byte-identical ISO), so a seed
string *is* a URL fragment away from being shareable. Worth adopting the shape:
`?seed=<seed>&mode=<mode>&<options>`.

### 2.3 Seeds carry metadata, not just a name
SotN's seeds expose **Knowledge Required**, **Modification Level**, **Relic Extension**,
**Castle Type**, **Minimum Complexity**. That is much better than our bare mode name: a player
wants to know *how hard* and *how weird* a seed is before committing hours to it. Our modes
have a `risk` string; this is the seed-level version of that, and it belongs in the seed
header and the GUI.

### 2.4 A generated seed card
SotN's **Bounty Hunter** preset generates shareable cards for a seed. Cheap to do, good for a
YouTube channel, and it doubles as the "here is your seed" receipt in the GUI.

### 2.5 Softlock and accessibility patches are a first-class feature
SotN ships **Accessibility Patches** (reduced flashing, visibility fixes, softlock patches)
and an **Anti-Freeze** patch. Two lessons:

1. Randomizers break games in ways the base game never anticipated, and patching the breakage
   is part of the product, not an afterthought.
2. **This is exactly the door problem.** Our own plan already flags that a blind door remap
   can strand the player or drop them into the endgame. SotN treats this as a solved category.

### 2.6 Dry running is a normal mode, and verbosity is a dial
`-vvv` deepening the report, and omitting both input and output giving a dry run, matches our
`--dry-run` and `#progress` stream. Validates the design; nothing to change.

## 3. Noted — relevant, not yet needed

### 3.1 The doors question has prior art, and it is separate for a reason
This is the most important single finding. In the SotN randomizer's own development guide,
under features that are **not** standard, is:

> *Randomizing where doors lead (There is an Area Randomizer developed by Mottzilla but there
> may be other compatibility issues depending on the preset.)*

So the flagship randomizer of the genre **does not randomize door destinations**, and a
dedicated separate tool exists for it, with known compatibility caveats. Two conclusions:

- Our instinct to treat doors as the hard, headline feature is correct — it is hard for
  everyone who has tried.
- The compatibility warning is real. A door remap has to be validated against progression
  flags, or it will break the game in ways a boot test will not catch. Hence the reachability
  guard in `PROJECT.md` §6 step 4.

Worth studying the Area Randomizer's approach directly before we commit to a design.

### 3.2 ECC/EDC recalculation — and why we probably do not need it
SotN's PPF workflow insists: *"After applying the patch, you must perform ECC/EDC
recalculation"*, with `error_recalc` / `ECCRegen`. That is because a PS1 `.bin` is
**MODE2/2352** — the raw 2352-byte-sector form, which carries error-correction codes that any
patch invalidates.

**Our image is different.** Summoner 1 is 1,232,699,392 bytes, which is exactly
601,904 × 2048 — a plain **2048-byte-sector ISO 9660** image with no ECC/EDC sectors. PCSX2
boots our patched discs directly, so nothing needs recalculating today. This becomes relevant
only if we ever emit a 2352-form image (e.g. for console/POPS-style distribution), at which
point we would need an ECC/EDC pass. Recorded here so the omission is a known choice, not an
oversight.

### 3.3 Emulator-side memory reading for verification
SotnRandoTools reads game memory through **SotnApi** on BizHawk to draw a live tracker. That is
the same problem as our doors verification: we need to know what the game is doing without
looking at it. Their answer is an emulator memory API; our plan is verbose emulog plus a
forced level load (`PROJECT.md` §6 step 5). If PCSX2's debugger/API can be driven headlessly,
that becomes a much better answer.

### 3.4 Reference decompilation
`sotn-decomp` exists as a full decompilation, and the randomizer is built on top of that kind
of knowledge. Our Ghidra/R5900 setup is the same play for Summoner, done from scratch because
no such project exists for it.

### 3.5 Packaging and launcher
The SotN launcher bundles emulator, timer, patcher, and an updater, and handles the
"no configuration required" experience. Our desktop app could grow a **Play in PCSX2** button
pointing at a built ISO — we already know the exact working invocation (`PROJECT.md` §7).

## 4. Rejected, and why

- **The Node/JS stack and `nexe` compilation.** Our engine is stdlib Python plus a .NET
  WinForms shell, chosen for this machine (no Node toolchain, 8 GB RAM, a desktop app the
  owner can double-click). Rewriting for ecosystem parity would cost a lot and gain nothing.
- **Presets as JSON files on disk, built by a bundler.** SotN's presets need
  `npm run build-presets` and edits in two index files; we have seen how that ages. Our modes
  are code-defined. If they become community-editable, they should be a single self-describing
  file the app reads directly — not a build step.
- **Distributing anything derived from the game.** Neither project ships game data, and
  neither will we. See `PROJECT.md` §8.
- **`turkeyMode`.** Genuinely charming. Not our problem. Noted for morale.

## 5. Net effect

Nothing in SotN changes the plan of record — it **confirms** it, and it gives us two
efficiency wins (patch-file output, seed strings as URLs) plus one warning worth heeding
(doors are hard for everyone, and the compatibility risk is real).
