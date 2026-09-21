# package-portable.ps1 - assemble the end-user bundle: a WinForms app + a frozen engine.
#
# The end user gets a folder they can copy to any Windows machine: no Python, no .NET to
# install, no network. They point it at their own legally dumped disc and get an ISO back.
#
#   powershell -File package-portable.ps1 [-Out <dir>] [-SkipFreeze] [-SkipPublish]
param(
    [string]$Out = "F:\rando\S1\out\SummonerRando-portable",
    [switch]$SkipFreeze,
    [switch]$SkipPublish
)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$stage = Join-Path $repo "work\portable-stage"
Write-Output "repo     : $repo"
Write-Output "output   : $Out"

# --- 1. the engine, frozen to one exe --------------------------------------
$frozen = Join-Path $stage "summoner-engine.exe"
if (-not $SkipFreeze) {
    Write-Output "`n[1/3] freezing the engine (PyInstaller one-file)..."
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Push-Location $repo
    try {
        python -m PyInstaller --onefile --console --name summoner-engine `
            --distpath $stage `
            --workpath (Join-Path $repo "work\pyi-build") `
            --specpath (Join-Path $repo "work\pyi-spec") `
            --collect-submodules pycdlib --noconfirm cli.py | Out-Null
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path $frozen)) { throw "frozen engine not found: $frozen" }
Write-Output ("      {0}  ({1:N1} MB)" -f $frozen, ((Get-Item $frozen).Length / 1MB))

# --- 2. the app, self-contained single file --------------------------------
$pub = Join-Path $repo "work\portable-publish"
if (-not $SkipPublish) {
    Write-Output "`n[2/3] publishing the WinForms app (self-contained, single file)..."
    dotnet publish (Join-Path $repo "desktop\SummonerRando.Desktop") -c Release -r win-x64 `
        --self-contained true -p:PublishSingleFile=true `
        -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:DebugType=none -o $pub | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed ($LASTEXITCODE)" }
}
$appExe = Join-Path $pub "SummonerRando.exe"
if (-not (Test-Path $appExe)) { throw "app exe not found: $appExe" }

# --- 3. assemble -----------------------------------------------------------
Write-Output "`n[3/3] assembling $Out ..."
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item $appExe $Out -Force
Copy-Item $frozen $Out -Force
@"
Summoner Randomizer - portable build
====================================

Run:  SummonerRando.exe

1. Browse to YOUR OWN Summoner disc image (.iso, SLUS-20074).
2. Pick a mode (No Enemies / Enemy Swarm / Enemy Difficulty / ... are in the list).
3. Set a seed, or press the dice for one.
4. Build ISO. The new disc is written where you point it; the seed is in the title bar.

This folder needs nothing installed: no Python, no .NET, no internet.

To PLAY a disc you build, the machine needs a PlayStation 2 emulator (or a real PS2).
The app looks for PCSX2, and the "Emulator..." button lets you point at pcsx2-qt.exe
if it is somewhere unusual. "Play ISO" then launches your finished disc. If there is no
emulator, the app says so - it does not ship one (PCSX2 is third-party software and
needs a BIOS you supply).

This build ships NO game data. Bring your own legally dumped disc - nothing is
downloaded, uploaded, or shared, and no disc is ever modified in place.

summoner-engine.exe is the randomizer engine; SummonerRando.exe drives it.
"@ | Set-Content -Path (Join-Path $Out "README.txt") -Encoding UTF8

Write-Output "`n--- bundle ---"
Get-ChildItem $Out | ForEach-Object { Write-Output ("  {0,-24} {1,10:N0} bytes" -f $_.Name, $_.Length) }
Write-Output "`nportable bundle ready: $Out"
