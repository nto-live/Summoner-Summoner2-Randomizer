# Packaging — the app the end user actually runs

*Written 2026-09-21, at the owner's instruction: **"This has to be an ISO for the end user"**,
**"A win form type app that generates an iso"**, **"And can be run on a separate computer"**.*

---

## 1. The contract, in one paragraph

The product is a **Windows desktop app** — WinForms, no browser, no server. The user picks a
Summoner disc image they own, picks a mode, sets (or is given) a seed, and presses **Build ISO**.
The app writes a **new ISO** of the same size that plays in PCSX2 or on real hardware. The seed
is shown in the window title as well as the seed box so it can be copied and shared. **The
deliverable is the ISO**, and the app is the thing that produces it.

It has to work on a machine that has none of the original development environment: no Python, no
`pip`, no .NET runtime, no copy of this workspace, no network.

## 2. What that implies

| Requirement | Why | How it is met |
|---|---|---|
| Nothing to install | the end user is a player, not a developer | .NET app published **self-contained, single file** (`win-x64`) |
| No Python on the target | the engine is Python | the engine is **frozen to `summoner-engine.exe`** (PyInstaller, one file) and shipped next to the app |
| No workspace paths | absolute paths from this machine must not leak | the engine is invoked with its own folder as the working directory; every input path (disc, output) comes from the user or the app |
| **The output must work in an emulator** | the whole point is a disc the user can play | the app never runs the game and takes no interest in which emulator is installed. What it guarantees is the **disc**: identical size, identical ISO9660 layout, byte-identical except the `TABLES.VPP` region, and every ISO built so far has booted in PCSX2 — several were played through (`DOOR-REMAP.md` §4.5, `ENEMIES.md` §4) |
| Same-size output | the archive is a sliced stream; offsets must not move | every transform is size-preserving by construction (see `ENEMIES.md`, `DOOR-REMAP.md`) |
| Shareable result | seeds should be reproducible and small to talk about | seed shown in the title bar; same seed + mode + options ⇒ byte-identical ISO |
| No game data shipped | legal rule, not a preference | the bundle contains code only; the user brings their own disc |

## 3. The bundle

```
SummonerRando\                     <- copy this folder anywhere; that is the install
  SummonerRando.exe                <- the WinForms app (self-contained, no .NET needed)
  summoner-engine.exe              <- the engine, frozen (no Python needed)
  README.txt                       <- "bring your own legally dumped disc"
```

That is the whole product. It is written to `F:\rando\S1\out\SummonerRando-portable\` by the
build script, and it is verified by running the engine executable from that folder on a machine
with no Python on `PATH`.

**The app does not run the game.** Its contract is exactly *ISO in, ISO out*: it hands back a disc
image and stops there. Whether that disc is played in PCSX2, another emulator, or on real
hardware is the user's business, and the app ships no emulator and looks for none.

What the app owes the user is that the returned ISO is a **valid, playable disc image**. That is
tested by booting it: every ISO built so far boots in PCSX2, and the door-remap and no-enemies
discs were watched loading levels (`DOOR-REMAP.md` §4.5, `ENEMIES.md` §4). The properties that make
it so are structural — same byte length, same ISO9660 directory, same boot ELF, nothing rewritten
outside the `TABLES.VPP` region.

### How the app finds the engine

`SummonerRando.Engine\EngineLocator.cs` already supports, in order:

1. an explicit override passed to the API,
2. `engine.txt` next to the app exe, containing a folder path,
3. `SUMMONER_RANDO_ENGINE`,
4. walking up from the app's base directory looking for `cli.py`.

Packaging adds one more rule, first: **if `summoner-engine.exe` sits in the resolved engine
folder, run that instead of `python cli.py`.** So the shipped layout above needs no configuration
at all, and a developer working from the workspace keeps using `cli.py` + their own Python.

## 4. Build the bundle

```powershell
# 1. freeze the engine (one file, pycdlib bundled)
python -m PyInstaller --onefile --name summoner-engine --console cli.py

# 2. publish the app self-contained, single file
dotnet publish desktop\SummonerRando.Desktop -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o desktop\publish-portable

# 3. assemble (does 1 and 2 for you, then copies both into one folder)
powershell -File package-portable.ps1
```

## 5. Status

| Piece | State |
|---|---|
| WinForms app, ISO in / ISO out, seed in the title | **built and working** (`desktop\Run.cmd`) |
| engine frozen to a single exe | **done** — `summoner-engine.exe`, 7.5 MB, one file, pycdlib inside |
| app prefers the frozen engine | **done** — `EngineClient.UsesFrozenEngine`; verified with Python removed from `PATH` |
| self-contained .NET publish | **done** — `SummonerRando.exe`, 161 MB, single file, no .NET needed |
| bundle assembled | **done** — `F:\rando\S1\out\SummonerRando-portable\` (app + engine + README.txt) |
| copy the folder to a clean machine and run | to do — the last proof, and it needs a second machine |

### How the portability was proven on this machine

With `PATH` cut down to `C:\Windows\system32` (so **no Python exists** for the app to find) and
`SUMMONER_RANDO_ENGINE` pointing at the bundle, the app's own plumbing ran four engine calls
through `summoner-engine.exe` and got real answers:

```
| $ F:\rando\S1\out\SummonerRando-portable\summoner-engine.exe --list        exit=0 json=True
  modes: 29  transforms: 37  option-aware: enemies_none, enemies_random, enemies_swarm,
                                      enemy_difficulty, levelcap_set, permadeath, ring_hunt, xp_scale
| $ …summoner-engine.exe --identify <disc>                                   exit=0  game=Summoner
| $ …summoner-engine.exe --seeds 1                                           seeds=PHS6OA
| $ …summoner-engine.exe --build <disc> --mode doors --seed HARNESS1 --dry-run  exit=0
```

The WinForms window was also rendered headlessly (`SummonerRando.Harness --screenshot`) with the
engine set to the frozen exe: the mode list shows **No Enemies**, and its **Options** pane shows
the `navpoint / team / both` disarm choice — so the new content reaches the end-user UI, not just
the CLI.

