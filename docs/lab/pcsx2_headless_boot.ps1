<#
  pcsx2_headless_boot.ps1 - boot a PS2 ISO in PCSX2 with no interactive desktop.

  Works as NT AUTHORITY\SYSTEM / Session 0. Two things are required, both
  verified on this host (PCSX2 2.8.1, Qt 6.11.1):

    1. QT_QPA_PLATFORM=windows
       The *native* Qt platform plugin works fine in Session 0 - Qt creates real
       (invisible) HWNDs. Do NOT use `offscreen`: PCSX2 2.8.1 creates a real GS
       device + swapchain for every renderer (even "Null"), and offscreen gives
       Qt no native window handle, so vkCreateSwapchainKHR fails and the VM
       never starts.

    2. PCSX2.ini must have SettingsVersion = 1
       Any other value makes PCSX2 pop a modal QMessageBox
       ("Settings failed to load, or are the incorrect version...") at startup.
       In a headless session that dialog can never be answered, so PCSX2 hangs
       forever at ~0.06 s CPU with no emulog.txt. This is the real trap.

  Example:
    .\pcsx2_headless_boot.ps1 -Iso F:\rando\S1\iso\Summoner.iso -Seconds 90
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Iso,
    [int]$Seconds = 90,
    [switch]$SlowBoot,
    [string]$DataPath,
    [string]$Exe = 'C:\Program Files\PCSX2\pcsx2-qt.exe',
    [switch]$KeepRunning
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Iso)) { throw "ISO not found: $Iso" }
if (-not (Test-Path -LiteralPath $Exe)) { throw "PCSX2 not found: $Exe" }

$docs = if ($DataPath) { $DataPath } else { Join-Path $env:USERPROFILE 'Documents\PCSX2' }
$ini  = Join-Path $docs 'inis\PCSX2.ini'
$emu  = Join-Path $docs 'logs\emulog.txt'

# --- preflight: the settings-version trap -----------------------------------
if (Test-Path -LiteralPath $ini) {
    $line = Select-String -Path $ini -Pattern '^\s*SettingsVersion\s*=' | Select-Object -First 1
    $ver  = if ($line) { ($line.Line -split '=')[1].Trim() } else { '<missing>' }
    if ($ver -ne '1') {
        Write-Warning "PCSX2.ini SettingsVersion = $ver (expected 1). PCSX2 will show a modal dialog and hang headlessly. Fixing it."
        (Get-Content -LiteralPath $ini -Raw) -replace '(?m)^\s*SettingsVersion\s*=.*$', 'SettingsVersion = 1' |
            Set-Content -LiteralPath $ini -NoNewline
    }
} else {
    Write-Warning "No PCSX2.ini at $ini - PCSX2 may run its setup wizard, which also blocks headlessly."
}

# --- launch ------------------------------------------------------------------
$env:QT_QPA_PLATFORM = 'windows'     # native, NOT offscreen
$env:QT_ASSUME_STDERR_HAS_CONSOLE = '1'

$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$logdir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'logs'
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$stdout = Join-Path $logdir "boot-$stamp.out.txt"
$stderr = Join-Path $logdir "boot-$stamp.err.txt"
$emuCopy = Join-Path $logdir "boot-$stamp.emulog.txt"

if (Test-Path -LiteralPath $emu) { Remove-Item -LiteralPath $emu -Force }

$argList = @('-batch', '-fastboot')
if ($SlowBoot) { $argList += '-slowboot' }
if ($DataPath) { $argList += @('-datapath', $DataPath) }
$argList += $Iso

Write-Host "launching: $Exe $($argList -join ' ')  (QT_QPA_PLATFORM=windows, ${Seconds}s)"
$p = Start-Process -FilePath $Exe -ArgumentList $argList -PassThru -NoNewWindow `
                   -RedirectStandardOutput $stdout -RedirectStandardError $stderr

$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $Seconds) {
    Start-Sleep -Seconds 5
    $proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
    if (-not $proc) { Write-Host "  [{0,5:N1}s] process exited (code {1})" -f ((Get-Date) - $t0).TotalSeconds, $p.ExitCode; break }
    Write-Host ("  [{0,5:N1}s] cpu={1,7:N2}s  rss={2,6:N0}MB  threads={3}" -f `
        ((Get-Date) - $t0).TotalSeconds, $proc.CPU, ($proc.WorkingSet64 / 1MB), $proc.Threads.Count)
}

$exitedOnOwn = -not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)
if (-not $exitedOnOwn -and -not $KeepRunning) {
    taskkill /F /T /PID $p.Id | Out-Null
}
if ($KeepRunning) { Write-Host "leaving pid $($p.Id) running (-KeepRunning)" }

if (Test-Path -LiteralPath $emu) { Copy-Item -LiteralPath $emu -Destination $emuCopy -Force }

# --- verdict -----------------------------------------------------------------
Write-Host ''
Write-Host "--- emulog: $emuCopy ---"
if (Test-Path -LiteralPath $emuCopy) {
    $keys = 'BIOS|Disc changed|Serial:|CRC:|VM subsystems initialized|ELF |executing|Error|Failed'
    Select-String -Path $emuCopy -Pattern $keys | ForEach-Object { Write-Host $_.Line }
    $text = Get-Content -LiteralPath $emuCopy -Raw
    Write-Host ''
    if ($text -match 'with entry point at 0x[0-9A-Fa-f]+ is executing') {
        Write-Host 'RESULT: PASS - BIOS loaded, disc read, boot ELF is executing.' -ForegroundColor Green
    } elseif ($text -match 'ELF Loading') {
        Write-Host 'RESULT: PARTIAL - ELF located but did not reach "executing".' -ForegroundColor Yellow
    } else {
        Write-Host 'RESULT: FAIL - no ELF activity; see log above.' -ForegroundColor Red
    }
} else {
    Write-Host 'RESULT: FAIL - no emulog.txt was produced (PCSX2 died before the VM started).' -ForegroundColor Red
}
Write-Host "stderr: $stderr"
