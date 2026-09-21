# Summoner Randomizer

A self-contained tool that takes **your own** Summoner disc image, applies randomized
changes, and writes a new disc image you can play in PCSX2 or on real hardware.

**This tool ships no game data.** No ISOs, no ROMs, no downloads, no links. You supply
the disc; it only ever writes a new ISO into `work/out/` on this machine. There is no
upload, no share, and no download endpoint.

---

## What the end user actually gets

**An ISO.** A Windows desktop app takes their own disc image, applies the changes they tick, and
writes a **new ISO of the same size** that plays in PCSX2 or on real hardware. The seed is shown
in the window title as well as the seed box, so it can be copied and shared.

The app is WinForms - no browser, no server, no localhost. And it is built to **run on a separate
computer**: the portable bundle is one folder holding the app and a frozen engine, with
**no Python, no .NET runtime and no network** required.

```
SummonerRando\           <- copy this folder anywhere; that is the install
  SummonerRando.exe      <- the app
  summoner-engine.exe    <- the engine, frozen (no Python needed)
  README.txt
```

Build it with `powershell -File package-portable.ps1` at the repo root. The recipe, and the
verification behind it, are in **`desktop\PACKAGING.md`**. Enemy modes (No Enemies, Enemy Swarm,
Enemy Difficulty) are documented in **`ENEMIES.md`**.

**What that machine needs is a PlayStation 2 emulator** (or real hardware) to *play* the result —
but that is not the app's business: the app takes an ISO and returns an ISO, and stops there. It
ships no emulator, looks for none, and never launches one. What it owes you is that the returned
disc is a valid, playable image: same size, same structure, only the data region rewritten — and
every ISO built so far has booted in PCSX2, several of them played through.

---

## Quick start

Double-click **`desktop\Run.cmd`** (or run `desktop\publish\SummonerRando.exe`).

Then: pick a disc → pick a mode → set a seed → **Build ISO**. The seed appears in the window
title as well as the seed box, so it is easy to copy and share. Build is disabled if the disc
is not one we can edit.

**There is no server.** The first version was a local web app; it is retired to
`_legacy-web-ui\`. The desktop app drives the engine directly.

Command line, if you prefer — `cli.py` is the engine and speaks JSON:

```
python cli.py --identify "D:\summoner.iso"           # what is this disc?
python cli.py --list                                 # modes, transforms, options, blocked
python cli.py --seeds 4                              # random seed suggestions
python cli.py --build "D:\summoner.iso" --mode roguelike --seed ABC123 --out out.iso
python cli.py --build "D:\summoner.iso" --mode doors --dry-run
```

Progress streams to stderr as `#progress …` and the result is one JSON object on stdout.
Exit codes: `0` ok · `2` refused (unsupported disc) · `1` error.

---

## What works, and what does not

| Disc | Archive format | Status |
|---|---|---|
| **Summoner** (PS2 2000, SLUS-20074) | VPP v1 | **Supported** |
| **Summoner 2** (PS2 2002, SLUS20448) | VPP v2 | Detected, **not editable yet** |

The app identifies a disc by volume ID *and* by archive fingerprint, so a disc with a
blank volume ID (the retail Summoner 1 disc has one) is still recognised. If you feed
it Summoner 2 it will say so plainly rather than appearing to do nothing.

### Modes

**25 modes, 33 transforms.** The full list, with measured edit counts and every per-mode
option, is in **`MODES.md`**.

Highlights: **Door Shuffle** · **Item Scatter** · Shop Shuffle · Chest Shuffle · Dialogue
Chaos · Sound and Visual Chaos · **Ring Hunt** and **Ring Hunt · Any Ring** (they change *how
the game ends*) · **Progression** (XP and level-cap dials) · Roguelike · **Hardcore** ·
Everything · Vanilla (baseline).

### Seeds are reproducible

The same seed with the same mode produces a **byte-identical** ISO. That is what makes
seed sharing and racing possible. Seeds that differ produce different builds.

### Honest status

Every transform is structurally sound, size-preserving and fully reversible, and the
resulting ISO is hash-clean. **Patched discs are now known to boot the real game** — that is
verified, not assumed:

```
test-roguelike.iso   15,235 edits    CRC 13E2774E   BIOS loaded, boot ELF executing
   test-endgame.iso   1 byte patched  CRC 13E2775E   BIOS loaded, boot ELF executing
     test-doors.iso   218 doors       CRC 13E2774E   BIOS loaded, boot ELF executing
```

`test-doors.iso` is the door remap: 218 `$Trigger:` destination names rewritten inside
`TABLES.VPP`, 1,679 changed bytes with **none** outside a declared field, image size
byte-identical. The unchanged CRC is the point — the executable was never touched. The mechanism,
the patch format and the honest limits are in **`DOOR-REMAP.md`**.

**But booting is not playing.** No mode has been watched through a cutscene, a door, or the
Forge opening — and a door remap in particular is unproven until something is seen coming out
the other side. Treat the pacing and progression transforms as promising, not proven.

---

## How it works

```
your ISO ──► identify ──► read TABLES.VPP ──► transform the script blob ──► write new ISO
```

1. **Identify** — volume ID + archive fingerprint tell us which game and which archive
   revision, and therefore whether we can edit it (`discover.py`).
2. **Read** — the game's data is not binary. `TABLES.VPP` holds a plain-text script
   language (doors, dialogue, spawns, triggers, items) sliced into 527 chunks.
3. **Transform** — the chunks are reassembled into one stream, edited, then written back
   into the same byte ranges.
4. **Write** — the image is copied and patched in place.

**Why edits must be size-preserving:** the 527 chunks are arbitrary slices of one
continuous stream — 424 of 526 boundaries cut mid-line. So the chunk boundaries are
meaningless to the game's loader, but they must not move. Every transform is therefore
length-neutral: values are swapped between equal-width fields, and flags are renamed
with same-length strings.

The whole ISO is never held in memory — only the ~7 MB script region is.

## Files

```
cli.py            the engine, JSON in / JSON out    <- the desktop app drives this
desktop/          the WinForms app
  Run.cmd             double-click launcher
  publish/            SummonerRando.exe (single file)
  SummonerRando.Engine/   runs cli.py, parses its JSON
  SummonerRando.Desktop/  the window
  SummonerRando.Harness/  console harness: drives the engine with no GUI
  _ui/                headless UI dumps (control tree + screenshots)
discover.py       disc identification + archive scan
rando_core.py     VPP reader, transforms, pipeline
binary.py         patches the executable inside the ISO
build.py          older standalone CLI (superseded by cli.py)
MODES.md          every mode and option, with real edit counts
PROJECT.md        the full project document
DOOR-REMAP.md     doors — mechanism, patch format, the 218-patch proof, DATA_PATCHES design
COMPILED-CODE.md  Ghidra toolchain, portal mechanism, the binary patcher
RESEARCH-SOTN.md  techniques consumed from the SotN randomizer
TIMER-DESIGN.md   timed runs (deferred by request)
_legacy-web-ui/   the retired server + browser UI, kept for the record
work/out/         generated ISOs
```

Only third-party requirement: `pycdlib` (`python -m pip install pycdlib`), used to read
the ISO9660 directory. Everything else is the standard library.

## Playing a build

- **PCSX2** — open the generated ISO directly.
- **Real hardware** — softmod (FreeMcBoot + OPL) or a modded console.

## Testing a build without a screen

The engine and the harness run headless, so a build can be checked on a machine with no
display — which is how this project is developed. The emulator needs one config value set:

> **`SettingsVersion` in `PCSX2.ini` must be `1`.** Any other value makes PCSX2 show a modal
dialog at startup and wait forever for a click. On a headless session that looks exactly like
a hang, with no log written at all.

Then:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
& pcsx2-qt.exe -batch -fastboot 'F:\path\to\build.iso'
```

`F:\rando\S1\notes\pcsx2_headless_boot.ps1` wraps this — it sets the value, runs with a
timeout, samples CPU, keeps a copy of `emulog.txt` and prints **PASS/PARTIAL/FAIL**.

## Rules this project holds to

- No game data is distributed, hosted, mirrored or linked — here or anywhere else.
- The verified source ISOs and part files on this machine are never wiped.
- Table-layer edits stay size-preserving until the archive slack question is resolved.
