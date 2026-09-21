# Summoner Randomizer — desktop app

A Windows Forms front end for the Summoner Randomizer engine. It takes an ISO,
lets you choose what to randomize, and writes a new ISO. **The seed is always
shown** — it is how runs are shared and compared.

There is no HTTP server and no browser. The app runs the engine
(`../cli.py`) as a subprocess: JSON in, JSON out, `#progress` lines streamed
into the log.

## Layout

```
desktop/
  SummonerRando.Engine/    class library: locates cli.py, runs it, parses its JSON
  SummonerRando.Desktop/   the WinForms window (SummonerRando.exe)
  SummonerRando.Harness/   console harness that drives the same plumbing (no GUI needed)
  Run.cmd                  double-click to launch
  publish/                 single-file exe output
```

## Build

```
dotnet build -c Release
```

## Publish a single-file exe

```
dotnet publish SummonerRando.Desktop -c Release -p:PublishSingleFile=true -r win-x64 --self-contained false -o publish
```

Produces `publish\SummonerRando.exe` (framework-dependent: needs the .NET 8
desktop runtime, which is already installed on this machine).

## Run

Double-click `Run.cmd`, or run `publish\SummonerRando.exe`.

## How the app finds the engine

In order:

1. `--engine <dir>` on the command line;
2. `engine.txt` next to the exe (one line: the engine folder path);
3. the `SUMMONER_RANDO_ENGINE` environment variable;
4. walking up from the exe's folder looking for `cli.py`.

Python 3.13 must be on `PATH` (override with `SUMMONER_RANDO_PYTHON`).

## Verify without a desktop session

`SummonerRando.Harness.exe` runs the same engine plumbing and prints the parsed
results, so the subprocess layer is testable in a non-interactive shell:

```
SummonerRando.Harness\bin\Release\net8.0\SummonerRando.Harness.exe "F:\rando\S1\iso\Summoner.iso"
```

The GUI itself needs a real desktop session to be seen.

## Notes

- **Nothing is uploaded, shared, or linked.** The app only reads the ISO you
  pick and writes the ISO you name. There is no disc distribution feature and
  none will be added.
- The engine's `pending` map (features that are blocked, and why) is shown in
  the "Not implemented (blocked)" panel so the app never pretends to do more
  than it does.
- Supported discs: Summoner 1 (VPP v1). Summoner 2 (VPP v2) is identified and
  refused with a reason; Build/Dry run stay disabled for it.
