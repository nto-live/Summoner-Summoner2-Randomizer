# PCSX2 2.8.1 headless boot — findings (2026-09-20)

Host: Windows 10.0.26200, running as **NT AUTHORITY\SYSTEM in Session 0**, no interactive
desktop (`explorer.exe` absent, `Win32_ComputerSystem.UserName` empty).
PCSX2 v2.8.1 (`C:\Program Files\PCSX2\pcsx2-qt.exe`), Qt 6.11.1, Intel N100 / UHD Graphics.

## TL;DR — working invocation

```powershell
$env:QT_QPA_PLATFORM = 'windows'
& 'C:\Program Files\PCSX2\pcsx2-qt.exe' -batch -fastboot 'F:\rando\S1\iso\Summoner.iso'
```

With `%USERPROFILE%\Documents\PCSX2\inis\PCSX2.ini` containing:

```ini
[UI]
SettingsVersion = 1
SetupWizardIncomplete = false

[Filenames]
BIOS = ps2-0120a-20000902.bin
```

Reusable, tested harness: **`F:\rando\S1\notes\pcsx2_headless_boot.ps1`**
(`-Iso <path> -Seconds 90`; exits PASS/PARTIAL/FAIL and saves a copy of emulog.txt).

## RESULT: full headless boot achieved

```
[ 0.3322] Loading BIOS...
[ 0.3333] BIOS Found: USA     v01.20(02/09/2000)  Console 20000902-234318
[ 0.4049] Disc changed to Summoner.iso.
[ 0.4049]   Serial: SLUS-20074
[ 0.4049]   CRC: 13E2774E
[ 3.3700] VM subsystems initialized in 3037.97 ms
[16.0839] ELF Loading: cdrom0:\SLUS_200.74;1, Game CRC = 13E2774E, EntryPoint = 0x00100008
[23.8718] ELF cdrom0:\SLUS_200.74;1 with entry point at 0x00100008 is executing.
```
CPU: ~19 s over a 70 s run (steady state ≈ 0.3–0.45 core), 20 threads, ~880 MB RSS.

## The two real blockers

### 1. `SettingsVersion` in PCSX2.ini must be `1`  ← the actual trap

Any other value (the staged config had `SettingsVersion = 3`) makes PCSX2 pop a **modal
QMessageBox** at startup and wait forever for a click that can never come in Session 0.

Symptom: process alive, ~0.06 s CPU, `Responding=True`, main thread `WaitReason=UserRequest`
(i.e. idle in a message loop), **no `emulog.txt`**, only Qt output like
`This plugin does not support propagateSizeHints()`.

How it was identified: `QT_LOGGING_RULES=qt.widgets.painting=true` + `QT_ASSUME_STDERR_HAS_CONSOLE=1`
showed a `QMessageBoxClassWindow` / `QLabel(name="qt_msgbox_label")` being painted
(`layoutBlock from= 0 to= 129` → text length 129). The only 129-char sentence-like UTF-16
string in `pcsx2-qt.exe` is:

> `Settings failed to load, or are the incorrect version. Clicking Yes will reset all settings to defaults. Do you want to continue?`

Brute-forcing `SettingsVersion` 1–10 confirmed it: **1 exits cleanly (code 0, no dialog)**;
2–10 all pop the dialog. (`-testconfig` with a valid config exits 0 with no output at all.)

The dialog is also why plain `-testconfig` "hung" and why `notepad`/`qwindows` looked broken —
the Qt `windows` platform plugin was fine the whole time.

### 2. `QT_QPA_PLATFORM=offscreen` cannot work — use the native `windows` plugin

`C:\Program Files\PCSX2\QtPlugins\platforms\` ships only `qwindows.dll` (no `qoffscreen.dll`).
A Qt-6.11.1 `qoffscreen.dll`/`qminimal.dll` was obtained from the PySide6-Essentials 6.11.1
wheel and made to load (it needs 1 export that PCSX2's Qt6Gui lacks:
`QPlatformIntegration::createPlatformVulkanInstance` — PCSX2 builds Qt with Vulkan disabled;
the plugin was binary-patched to alias that one import, which is safe because the method is the
*last* virtual in `QPlatformIntegration`).

Even then, offscreen is a dead end, because **PCSX2 2.8.1 creates a real GS device + swapchain
for every renderer, including `Null`** (`GS/GS.cpp`: `GetAPIForRenderer()` falls through to
`GSUtil::GetPreferredRenderer()` for anything unusual). With offscreen, Qt has no native window
handle, so:

```
[ 1.8596] QueryDisplayConfig()/MonitorFromWindow() failed: Win32 Error 1400: Invalid window handle.
[ 1.8661] (CreateSwapChain) vkCreateSwapchainKHR failed: (-1: VK_ERROR_OUT_OF_HOST_MEMORY)
[ 1.8662] Failed to create swap chain
```

The **native `windows` platform plugin works fine in Session 0** — Qt creates real, invisible
HWNDs, so the Vulkan/DX swapchain succeeds and the VM boots. (Harmless noise it prints:
`SetProcessDpiAwarenessContext() failed: Access is denied`,
`QueryDisplayConfig() failed: Win32 Error 5: Access is denied`.)

### Notes / dead ends

* `Renderer = 11` (Null) is *not* required and does not avoid the swapchain; it is honoured
  (`[Unsafe Settings] Graphics API is not set to Automatic`) but still builds the preferred
  hardware device. Left unset (= Automatic → Vulkan on this Intel GPU).
* SPU2 default **Cubeb** works with no audio endpoint present — no change needed.
* `-nogui` is unnecessary and does not help.
* BIOS path: an **absolute** path in `[Filenames] BIOS` is rejected
  (`Configured BIOS '...' does not exist, trying to find an alternative.` → silently falls back
  to a random/Japan dump). Use the **bare filename**; PCSX2 then loads the intended USA v01.20 BIOS.
* `.nvm` / `rom1` / `rom2` "not found" warnings are normal on a fresh data dir.
* Only `%USERPROFILE%\Documents\PCSX2\` was written; `F:\rando\S1\iso\` and `parts\` untouched.
* Original staged ini preserved as `F:\rando\S1\notes\PCSX2.ini.bak` (`SettingsVersion = 3`).
* Nothing was installed system-wide; the PySide6 plugin DLLs were removed again, so
  `C:\Program Files\PCSX2\QtPlugins\platforms\` is back to just `qwindows.dll`.

## Useful probe scripts left in this folder

| File | Purpose |
|---|---|
| `pcsx2_headless_boot.ps1` | **main deliverable** — boot an ISO headlessly, PASS/FAIL verdict |
| `run_pcsx2.py` | run with a hard timeout, dump stdout/stderr |
| `probe_run.py` | sample CPU/threads/file changes over time |
| `test_version.py` | brute-force `SettingsVersion` and detect the blocking dialog |
| `find_dialog.py`, `sentences.py`, `memscan_pid.py` | find a blocking QMessageBox' text |
| `peinfo.py`, `pe_diff.py` | PE import/export diffing for Qt plugin compatibility |
| `pcsx2-src.zip` | PCSX2 v2.8.1 source (used to trace renderer/config code) |
