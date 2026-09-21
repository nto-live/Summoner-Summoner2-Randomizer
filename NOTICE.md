# NOTICE — no game material lives in this repository

This project is a fan-made randomizer for a game the user already owns. It ships **no game data
of any kind**, and that applies to the repository itself, not just to the application:

* no disc images — not the original, not any build produced from it
* no extracted assets: no textures, models, audio, movies, level geometry
* no dialogue, quest text, item descriptions or any other creative content of the game
* no bulk dump of the game's files, and no dumps of its data tables
* no emulator, no BIOS, no third-party tool

## What is in here

* **Our own code** — the engine, the transforms, the desktop app, the test rig.
* **Our own writing** — the design notes, the findings, the dead ends, the statement of work.
* **Minimal structural description of the game's file formats**: field names and keys
  (`+Monster`, `$Trigger:`), byte offsets, record sizes, counts, and where things live. This is
  interoperability information — the same class of fact a format specification contains — and it
  is what makes a randomizer possible at all.
* **A short number of narrow reconstructions** of what specific game routines do, written in our
  own pseudocode with our own annotations, where a prose sentence would not be precise enough.
  They describe behaviour; they are not listings of the game's code, and they are not usable as
  the game.
* **Our own test output** — logs, screenshots of *our* application, verification reports.

## What is deliberately missing

The full disassembly, the extracted data stream, the symbol maps, and the record inventories stay
on the development machine, outside the repository. Where a document needs to refer to one of
them it says so by path instead of including it.

## How it is enforced

`tools/check-no-game-data.py` walks every file git tracks and fails if it finds:

1. a forbidden file type (a disc image, an executable, an archive payload, a save state),
2. a file too large to be source,
3. **a run of text that also appears verbatim in the game's own text stream** — the real check,
   run against the extracted stream on the development machine, with a 60-character threshold.

```powershell
python tools/check-no-game-data.py
```

Run it before every push. It exits `1` and names the file and the run if it finds something.

## If a check fires

Take the material out, or explain it here. "It is only a few lines" is not a reason on its own —
the test is whether it is *necessary to describe the format*, not how long it is.
